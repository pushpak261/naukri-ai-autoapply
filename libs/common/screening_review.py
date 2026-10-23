"""Tenant-local, durable questions and confirmed answers shared by agent and dashboard."""

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from libs.common.screening import format_evidence, question_key


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
                use_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS questions_by_key ON questions(question_key,updated_at DESC);
        """
        )
        connection.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(questions)")}
        if "resolved_from_facts" not in columns:
            connection.execute(
                "ALTER TABLE questions ADD COLUMN resolved_from_facts INTEGER NOT NULL DEFAULT 0"
            )
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _key(question, job):
        key = question_key(question.get("question", ""))
        if re.search(
            r"\b(?:our company|this company|this role|this position|our organization|why.*join|why.*interested|why should we hire|how.*(?:skills|experience).*match|cover letter|motivation|consent|agreement|signature|declaration)\b",
            key,
        ):
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
        identity = json.dumps([question_key(text), field, options], ensure_ascii=False)
        return hashlib.sha256(identity.encode()).hexdigest(), text, field, options

    def remember(self, question, job):
        identifier, text, field, options = self.metadata(question)
        key = self._key(question, job)
        identifier = hashlib.sha256((identifier + key).encode()).hexdigest()
        if not text:
            return
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO questions(id, question_key, question, field_type, options, updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, resolved_from_facts=0",
                (identifier, key, text, field, json.dumps(options), datetime.now(UTC).isoformat()),
            )
            job_id = getattr(job, "id", None)
            if isinstance(job_id, int) and job_id > 0:
                connection.execute(
                    "INSERT OR IGNORE INTO affected_jobs VALUES(?,?,?)",
                    (identifier, job_id, str(getattr(job, "title", ""))[:300]),
                )
        return identifier

    def mark_resolved_from_facts(self, question, job):
        """Close a validated field's pending prompt without caching it as a user answer."""
        identifier, _, _, _ = self.metadata(question)
        identifier = hashlib.sha256((identifier + self._key(question, job)).encode()).hexdigest()
        with self._connect() as connection:
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
                "SELECT id, answer, updated_at, 'confirmed' AS source, '' AS context_hash FROM questions WHERE question_key=? AND answer<>'' ORDER BY updated_at DESC",
                (self._key(question, job),),
            ).fetchall()
            if not rows and context_hash:
                rows = connection.execute(
                    "SELECT q.id, m.answer, m.updated_at, m.source, m.context_hash FROM questions q JOIN answer_memory m ON m.question_id=q.id "
                    "WHERE q.question_key=? AND m.context_hash=? AND m.source IN ('profile','technical') ORDER BY m.updated_at DESC",
                    (self._key(question, job), context_hash),
                ).fetchall()
            if not rows:
                return ""
            # A correction replaces the earlier answer. Never fall back to an
            # older value when the latest answer cannot fit this field's options.
            latest = [row for row in rows if row["updated_at"] == rows[0]["updated_at"]]
            answers = {
                format_evidence(row["answer"], question, experience_in_years=False)
                for row in latest
            }
            if len(answers) != 1 or not next(iter(answers)):
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
            return next(iter(answers))

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
                "SELECT q.id,q.question,q.question_key,q.field_type,q.options,"
                "CASE WHEN q.answer<>'' THEN q.answer ELSE m.answer END AS answer,"
                "CASE WHEN q.answer<>'' THEN 'confirmed' ELSE m.source END AS source,"
                "CASE WHEN q.answer<>'' THEN q.updated_at ELSE m.updated_at END AS updated_at,"
                "COALESCE(m.use_count,0) AS use_count,COALESCE(m.last_used_at,'') AS last_used_at "
                "FROM questions q LEFT JOIN answer_memory m ON m.question_id=q.id "
                "WHERE (q.answer<>'' OR m.answer<>'') AND q.question LIKE ? ORDER BY updated_at DESC LIMIT ?",
                ("%" + search + "%", limit),
            ).fetchall()
            total = connection.execute(
                "SELECT COUNT(*) FROM questions q LEFT JOIN answer_memory m ON m.question_id=q.id WHERE q.answer<>'' OR m.answer<>''"
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

    def pending(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM questions WHERE answer='' AND resolved_from_facts=0 ORDER BY updated_at DESC LIMIT 100"
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
                            "SELECT job_id, title FROM affected_jobs WHERE question_id=?",
                            (row["id"],),
                        )
                    ],
                }
                for row in rows
            ]

    def save_answers(self, answers):
        """Validate the complete batch before changing any answer."""
        with self._connect() as connection:
            resolved = []
            jobs = set()
            for identifier, value in answers.items():
                row = connection.execute(
                    "SELECT * FROM questions WHERE id=?", (identifier,)
                ).fetchone()
                if row is None:
                    raise ValueError("Screening question no longer exists")
                value = str(value).strip()
                if not value or len(value) > 2000 or row["field_type"] == "file":
                    raise ValueError(
                        "Supply a non-empty answer; attachments require the native form"
                    )
                metadata = {
                    "question": row["question"],
                    "type": row["field_type"],
                    "options": json.loads(row["options"]),
                }
                formatted = format_evidence(value, metadata, experience_in_years=False)
                if not formatted:
                    raise ValueError("Answer must match the available options and field format")
                if row["field_type"] == "date":
                    from datetime import date

                    try:
                        date.fromisoformat(formatted)
                    except ValueError as error:
                        raise ValueError("Date answers must use YYYY-MM-DD") from error
                resolved.append((formatted, datetime.now(UTC).isoformat(), identifier))
                jobs.update(
                    job[0]
                    for job in connection.execute(
                        "SELECT job_id FROM affected_jobs WHERE question_id=?", (identifier,)
                    )
                )
            connection.executemany(
                "UPDATE questions SET answer=?, updated_at=? WHERE id=?", resolved
            )
            connection.executemany(
                "INSERT INTO answer_memory(question_id,answer,source,context_hash,updated_at) VALUES(?,?,'confirmed','',?) "
                "ON CONFLICT(question_id) DO UPDATE SET answer=excluded.answer,source='confirmed',context_hash='',updated_at=excluded.updated_at",
                [(identifier, value, now) for value, now, identifier in resolved],
            )
            # Queue only jobs whose entire known question set is resolved.
            return sorted(
                job_id
                for job_id in jobs
                if not connection.execute(
                    "SELECT 1 FROM affected_jobs j JOIN questions q ON q.id=j.question_id WHERE j.job_id=? AND q.answer='' AND q.resolved_from_facts=0 LIMIT 1",
                    (job_id,),
                ).fetchone()
            )
