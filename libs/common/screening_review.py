"""Tenant-local, durable questions and confirmed answers shared by agent and dashboard."""

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from libs.common.screening import format_evidence, question_key
from libs.common.screening_intents import answer_identity, job_specific_question


class ScreeningReviewStore:
    def __init__(self, project_root):
        self.path = Path(project_root) / "data" / "screening_review.db"

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY, question_key TEXT NOT NULL, question TEXT NOT NULL,
                field_type TEXT NOT NULL, options TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS affected_jobs (
                question_id TEXT NOT NULL REFERENCES questions(id), job_id INTEGER NOT NULL,
                title TEXT NOT NULL, PRIMARY KEY(question_id, job_id)
            );
            CREATE TABLE IF NOT EXISTS employer_links (
                job_key TEXT PRIMARY KEY, url TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS answer_memory (
                question_id TEXT PRIMARY KEY REFERENCES questions(id),
                answer TEXT NOT NULL, source TEXT NOT NULL, context_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL, last_used_at TEXT NOT NULL DEFAULT '',
                use_count INTEGER NOT NULL DEFAULT 0, confirmed_revision INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS questions_by_key ON questions(question_key,updated_at DESC);
            CREATE TABLE IF NOT EXISTS memory_version (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL);
            INSERT OR IGNORE INTO memory_version VALUES(1,0);
        """
        )
        connection.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(questions)")}
        if "resolved_from_facts" not in columns:
            connection.execute(
                "ALTER TABLE questions ADD COLUMN resolved_from_facts INTEGER NOT NULL DEFAULT 0"
            )
        memory_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(answer_memory)")
        }
        if "confirmed_revision" not in memory_columns:
            connection.execute(
                "ALTER TABLE answer_memory ADD COLUMN confirmed_revision INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS screening_schema (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        )
        if connection.execute("SELECT 1 FROM screening_schema WHERE id=1").fetchone() is None:
            changed = False
            for row in connection.execute(
                "SELECT id,question,question_key FROM questions"
            ).fetchall():
                _, separator, scope = row["question_key"].partition(" | job ")
                key = answer_identity(row["question"]) + (separator + scope if separator else "")
                if key != row["question_key"]:
                    connection.execute(
                        "UPDATE questions SET question_key=? WHERE id=?", (key, row["id"])
                    )
                    changed = True
            if changed:
                connection.execute("UPDATE memory_version SET revision=revision+1 WHERE id=1")
            connection.execute("INSERT INTO screening_schema VALUES(1,1)")
        if connection.execute("SELECT version FROM screening_schema WHERE id=1").fetchone()[0] < 2:
            connection.execute(
                "UPDATE questions SET resolved_from_facts=1 WHERE answer='' AND "
                "(LOWER(question) LIKE 'save job%' OR LOWER(question) LIKE 'save this job%' OR LOWER(question) LIKE 'bookmark job%')"
            )
            connection.execute("UPDATE screening_schema SET version=2 WHERE id=1")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _key(question, job):
        key = answer_identity(question.get("question", ""))
        if job_specific_question(question.get("question", "")):
            identifier = getattr(job, "naukri_job_id", "")
            if not identifier and getattr(job, "linkedin_job_id", ""):
                identifier = "linkedin:" + str(job.linkedin_job_id)
            key += " | job " + str(identifier or getattr(job, "id", ""))
        return key

    @staticmethod
    def metadata(question):
        text = str(question.get("question", "")).strip()[:1000]
        field = question.get("input_type") or question.get("type", "text")
        if field not in ("number", "date", "file"):
            field = "text"
        options = [
            str(o.get("text", "") if isinstance(o, dict) else o).strip()[:1000]
            for o in question.get("options", [])[:100]
        ]
        options = list(dict.fromkeys(o for o in options if o))
        identity = json.dumps([question_key(text), field, sorted(options)], ensure_ascii=False)
        return hashlib.sha256(identity.encode()).hexdigest(), text, field, options

    @staticmethod
    def _existing_identifier(connection, identifier, key, field, options):
        # Older records hashed option order. Reuse their IDs without deleting
        # confirmations or breaking an already open review editor.
        rows = connection.execute(
            "SELECT id,options FROM questions WHERE question_key=? AND field_type=? ORDER BY updated_at DESC,id",
            (key, field),
        ).fetchall()
        for row in rows:
            previous = json.loads(row["options"])
            if sorted(previous) == sorted(options):
                return row["id"]
            if (
                len(options) > 1
                and len(previous) == 1
                and answer_identity(previous[0]) == key.partition(" | job ")[0]
            ):
                # An older extractor mistook the question heading for its only
                # option. Retain its ID/history, but retire that unusable prompt.
                connection.execute(
                    "UPDATE questions SET resolved_from_facts=1 WHERE id=? AND answer=''",
                    (row["id"],),
                )
        return identifier

    def remember(self, question, job):
        identifier, text, field, options = self.metadata(question)
        key = self._key(question, job)
        identifier = hashlib.sha256((identifier + key).encode()).hexdigest()
        if not text:
            return
        with self._connect() as connection:
            identifier = self._existing_identifier(connection, identifier, key, field, options)
            connection.execute(
                "INSERT INTO questions(id, question_key, question, field_type, options, updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, resolved_from_facts=0",
                (identifier, key, text, field, json.dumps(options), datetime.now(UTC).isoformat()),
            )
            job_id = self._dashboard_job_id(job)
            if isinstance(job_id, int) and job_id > 0:
                connection.execute(
                    "INSERT OR IGNORE INTO affected_jobs VALUES(?,?,?)",
                    (identifier, job_id, str(getattr(job, "title", ""))[:300]),
                )
        return identifier

    def _dashboard_job_id(self, job):
        """LinkedIn's private database IDs must never queue unrelated dashboard jobs."""
        linkedin_id = getattr(job, "linkedin_job_id", "")
        if not linkedin_id:
            return getattr(job, "id", None)
        database = self.path.with_name("naukri_agent.db")
        if not database.is_file():
            return None
        try:
            with closing(
                sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
            ) as connection:
                row = connection.execute(
                    "SELECT id FROM jobs WHERE naukri_job_id=? AND source='linkedin'",
                    ("li_" + str(linkedin_id),),
                ).fetchone()
                return row[0] if row else None
        except sqlite3.DatabaseError:
            return None

    def mark_resolved_from_facts(self, question, job):
        """Close a validated field's pending prompt without caching it as a user answer."""
        identifier, _, field, options = self.metadata(question)
        key = self._key(question, job)
        identifier = hashlib.sha256((identifier + key).encode()).hexdigest()
        with self._connect() as connection:
            identifier = self._existing_identifier(connection, identifier, key, field, options)
            connection.execute(
                "UPDATE questions SET resolved_from_facts=1 WHERE id=? AND answer=''",
                (identifier,),
            )

    @staticmethod
    def _employer_key(job):
        for platform in ("naukri", "linkedin"):
            identifier = getattr(job, platform + "_job_id", "")
            if identifier:
                return platform + ":" + str(identifier)
        return ""

    def remember_employer_url(self, job, url):
        key = self._employer_key(job)
        if key:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO employer_links VALUES(?,?) ON CONFLICT(job_key) DO UPDATE SET url=excluded.url",
                    (key, url),
                )

    def employer_url_for(self, job):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT url FROM employer_links WHERE job_key=?", (self._employer_key(job),)
            ).fetchone()
        return row["url"] if row else ""

    def answer_for(self, question, job, context_hash=""):
        # Exact wording/units only; a different question must never inherit a
        # fuzzy cached answer about another employer, skill or declaration.
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT q.id,q.answer,q.updated_at,'confirmed' AS source,'' AS context_hash,COALESCE(m.confirmed_revision,0) AS version "
                "FROM questions q LEFT JOIN answer_memory m ON m.question_id=q.id WHERE q.question_key=? AND q.answer<>'' "
                "ORDER BY version DESC,q.updated_at DESC",
                (self._key(question, job),),
            ).fetchall()
            if not rows and context_hash:
                rows = connection.execute(
                    "SELECT q.id, m.answer, m.updated_at, m.source, m.context_hash, 0 AS version FROM questions q JOIN answer_memory m ON m.question_id=q.id "
                    "WHERE q.question_key=? AND m.context_hash=? AND m.source IN ('profile','technical') ORDER BY m.updated_at DESC",
                    (self._key(question, job), context_hash),
                ).fetchall()
            if not rows:
                return ""
            # A correction replaces the earlier answer. Never fall back to an
            # older value when the latest answer cannot fit this field's options.
            latest = [
                row
                for row in rows
                if row["version"] == rows[0]["version"]
                and (row["version"] > 0 or row["updated_at"] == rows[0]["updated_at"])
            ]
            answers = {
                format_evidence(row["answer"], question, experience_in_years=False)
                for row in latest
            }
            if len(answers) != 1 or not next(iter(answers)):
                return ""
            answer = next(iter(answers))
            minimum, maximum = question.get("min_length"), question.get("max_length")
            if (isinstance(minimum, int) and len(answer) < minimum) or (
                isinstance(maximum, int) and maximum > 0 and len(answer) > maximum
            ):
                return ""
            row = latest[0]
            connection.execute(
                "INSERT INTO answer_memory(question_id,answer,source,context_hash,updated_at,last_used_at,use_count) VALUES(?,?,?,?,?,?,1) "
                "ON CONFLICT(question_id) DO UPDATE SET use_count=use_count+1,last_used_at=excluded.last_used_at",
                (
                    row["id"],
                    row["answer"],
                    row["source"],
                    row["context_hash"],
                    row["updated_at"],
                    datetime.now(UTC).isoformat(),
                ),
            )
            return answer

    def observe(self, question, answer, job, source, context_hash):
        """Remember provenance without promoting a generated answer to user confirmation."""
        if source not in ("profile", "technical", "ai_suggestion"):
            return
        identifier, text, field, options = self.metadata(question)
        if not text or field == "file" or question.get("type") == "password":
            return
        formatted = format_evidence(answer, question, experience_in_years=False)
        if not formatted or len(formatted) > 2000:
            return
        key = self._key(question, job)
        identifier = hashlib.sha256((identifier + key).encode()).hexdigest()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            identifier = self._existing_identifier(connection, identifier, key, field, options)
            connection.execute(
                "INSERT OR IGNORE INTO questions(id,question_key,question,field_type,options,updated_at,resolved_from_facts) VALUES(?,?,?,?,?,?,1)",
                (identifier, key, text, field, json.dumps(options), now),
            )
            connection.execute(
                "INSERT INTO answer_memory(question_id,answer,source,context_hash,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(question_id) DO UPDATE SET answer=excluded.answer,source=excluded.source,context_hash=excluded.context_hash,updated_at=excluded.updated_at",
                (identifier, formatted, source, context_hash, now),
            )
        return identifier

    def memory(self, search="", limit=100):
        with self._connect() as connection:
            rows = connection.execute(
                "WITH entries AS (SELECT q.id,q.question,q.question_key,q.field_type,q.options,"
                "CASE WHEN q.answer<>'' THEN q.answer ELSE m.answer END AS answer,"
                "CASE WHEN q.answer<>'' THEN 'confirmed' ELSE m.source END AS source,"
                "CASE WHEN q.answer<>'' THEN q.updated_at ELSE m.updated_at END AS updated_at,"
                "COALESCE(m.confirmed_revision,0) AS version,"
                "COALESCE(m.use_count,0) AS uses,COALESCE(m.last_used_at,'') AS last_used "
                "FROM questions q LEFT JOIN answer_memory m ON m.question_id=q.id "
                "WHERE q.answer<>'' OR m.answer<>''), ranked AS (SELECT *,"
                "ROW_NUMBER() OVER (PARTITION BY question_key ORDER BY (source='confirmed') DESC,version DESC,updated_at DESC,id) AS position,"
                "SUM(uses) OVER (PARTITION BY question_key) AS use_count,"
                "MAX(last_used) OVER (PARTITION BY question_key) AS last_used_at FROM entries) "
                "SELECT id,question,question_key,field_type,options,answer,source,updated_at,use_count,last_used_at "
                "FROM ranked WHERE position=1 AND question LIKE ? ORDER BY updated_at DESC,id LIMIT ?",
                ("%" + search + "%", limit),
            ).fetchall()
            total = connection.execute(
                "SELECT COUNT(DISTINCT q.question_key) FROM questions q LEFT JOIN answer_memory m ON m.question_id=q.id WHERE q.answer<>'' OR m.answer<>''"
            ).fetchone()[0]
        items = []
        for row in rows:
            item = dict(row)
            item["scope"] = "job" if " | job " in item.pop("question_key") else "profile"
            item["options"] = json.loads(item["options"])
            items.append(item)
        return {"items": items, "total": total}

    def forget(self, identifier):
        """Forget matching variants too, so an older answer cannot reappear."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT question_key FROM questions WHERE id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise ValueError("Remembered answer no longer exists")
            connection.execute(
                "DELETE FROM answer_memory WHERE question_id IN (SELECT id FROM questions WHERE question_key=?)",
                (row["question_key"],),
            )
            connection.execute(
                "DELETE FROM affected_jobs WHERE question_id IN (SELECT id FROM questions WHERE question_key=?)",
                (row["question_key"],),
            )
            connection.execute("DELETE FROM questions WHERE question_key=?", (row["question_key"],))
            connection.execute("UPDATE memory_version SET revision=revision+1 WHERE id=1")

    def revision(self):
        with self._connect() as connection:
            return connection.execute("SELECT revision FROM memory_version WHERE id=1").fetchone()[
                0
            ]

    def pending(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM (SELECT *,ROW_NUMBER() OVER (PARTITION BY question_key ORDER BY updated_at DESC,id) AS position "
                "FROM questions WHERE answer='' AND resolved_from_facts=0) "
                "WHERE position=1 ORDER BY updated_at DESC,id LIMIT 100"
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "question": row["question"],
                    "field_type": row["field_type"],
                    "options": json.loads(row["options"]),
                    "jobs": [
                        dict(job)
                        for job in connection.execute(
                            "SELECT j.job_id,MAX(j.title) AS title FROM affected_jobs j JOIN questions q ON q.id=j.question_id "
                            "WHERE q.question_key=? AND q.answer='' AND q.resolved_from_facts=0 GROUP BY j.job_id ORDER BY j.job_id",
                            (row["question_key"],),
                        )
                    ],
                }
                for row in rows
            ]

    @staticmethod
    def _format_for_row(value, row):
        if row["field_type"] == "file":
            return ""
        metadata = {
            "question": row["question"],
            "type": row["field_type"],
            "options": json.loads(row["options"]),
        }
        formatted = format_evidence(value, metadata, experience_in_years=False)
        if formatted and row["field_type"] == "date":
            from datetime import date

            try:
                date.fromisoformat(formatted)
            except ValueError:
                return ""
        return formatted

    def _confirmation_value(self, value, row):
        value = str(value).strip()
        if not value or len(value) > 2000 or row["field_type"] == "file":
            raise ValueError("Supply a non-empty answer; attachments require the native form")
        formatted = self._format_for_row(value, row)
        if not formatted:
            if row["field_type"] == "date":
                raise ValueError("Date answers must use YYYY-MM-DD")
            raise ValueError("Answer must match the available options and field format")
        return formatted

    def _resolve_compatible_variants(self, connection, confirmed_keys):
        for key, value in confirmed_keys.items():
            variants = connection.execute(
                "SELECT * FROM questions WHERE question_key=? AND answer=''", (key,)
            ).fetchall()
            for variant in variants:
                # Keep format-specific records for validation, but a known
                # compatible answer needs no second confirmation.
                options = json.loads(variant["options"])
                obsolete = (
                    len(options) == 1 and answer_identity(options[0]) == key.partition(" | job ")[0]
                )
                compatible = obsolete or self._format_for_row(value, variant)
                connection.execute(
                    "UPDATE questions SET resolved_from_facts=? WHERE id=?",
                    (int(bool(compatible)), variant["id"]),
                )

    def save_answers(self, answers):
        """Validate the complete batch before changing any answer."""
        with self._connect() as connection:
            resolved = []
            jobs = set()
            confirmed_keys = {}
            for identifier, value in answers.items():
                row = connection.execute(
                    "SELECT * FROM questions WHERE id=?", (identifier,)
                ).fetchone()
                if row is None:
                    raise ValueError("Screening question no longer exists")
                formatted = self._confirmation_value(value, row)
                if row["question_key"] in confirmed_keys:
                    raise ValueError("Supply one confirmation per screening question")
                confirmed_keys[row["question_key"]] = formatted
                resolved.append((formatted, datetime.now(UTC).isoformat(), identifier))
                jobs.update(
                    job[0]
                    for job in connection.execute(
                        "SELECT j.job_id FROM affected_jobs j JOIN questions q ON q.id=j.question_id WHERE q.question_key=?",
                        (row["question_key"],),
                    )
                )
            connection.executemany(
                "UPDATE questions SET answer=?, updated_at=? WHERE id=?", resolved
            )
            connection.executemany(
                "INSERT INTO answer_memory(question_id,answer,source,context_hash,updated_at,confirmed_revision) VALUES(?,?,'confirmed','',?,(SELECT revision+1 FROM memory_version WHERE id=1)) "
                "ON CONFLICT(question_id) DO UPDATE SET answer=excluded.answer,source='confirmed',context_hash='',updated_at=excluded.updated_at,confirmed_revision=excluded.confirmed_revision",
                [(identifier, value, now) for value, now, identifier in resolved],
            )
            connection.execute("UPDATE memory_version SET revision=revision+1 WHERE id=1")
            self._resolve_compatible_variants(connection, confirmed_keys)
            # Queue only jobs whose entire known question set is resolved.
            return sorted(
                job_id
                for job_id in jobs
                if not connection.execute(
                    "SELECT 1 FROM affected_jobs j JOIN questions q ON q.id=j.question_id WHERE j.job_id=? AND q.answer='' AND q.resolved_from_facts=0 LIMIT 1",
                    (job_id,),
                ).fetchone()
            )
