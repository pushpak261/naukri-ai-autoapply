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
        """
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
            r"\b(?:our company|this company|this role|our organization|why.*join|why.*interested)\b",
            key,
        ):
            key += " | job " + str(getattr(job, "naukri_job_id", "") or getattr(job, "id", ""))
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
                "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
                (identifier, key, text, field, json.dumps(options), datetime.now(UTC).isoformat()),
            )
            job_id = getattr(job, "id", None)
            if isinstance(job_id, int) and job_id > 0:
                connection.execute(
                    "INSERT OR IGNORE INTO affected_jobs VALUES(?,?,?)",
                    (identifier, job_id, str(getattr(job, "title", ""))[:300]),
                )
        return identifier

    def answer_for(self, question, job):
        # Exact wording/units only; a different question must never inherit a
        # fuzzy cached answer about another employer, skill or declaration.
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT answer FROM questions WHERE question_key=? AND answer<>''",
                (self._key(question, job),),
            ).fetchall()
        answers = {
            format_evidence(row["answer"], question, experience_in_years=False) for row in rows
        }
        answers.discard("")
        return next(iter(answers)) if len(answers) == 1 else ""

    def pending(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM questions WHERE answer='' ORDER BY updated_at DESC LIMIT 100"
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
            # Queue only jobs whose entire known question set is resolved.
            return sorted(
                job_id
                for job_id in jobs
                if not connection.execute(
                    "SELECT 1 FROM affected_jobs j JOIN questions q ON q.id=j.question_id WHERE j.job_id=? AND q.answer='' LIMIT 1",
                    (job_id,),
                ).fetchone()
            )
