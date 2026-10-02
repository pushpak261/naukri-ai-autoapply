"""Tests for domain entities, ORM reprs, and the migration helper."""

import pytest
from sqlalchemy import create_engine, text

from src.naukri_agent.models import db_schema as schema
from src.naukri_agent.models.entities import Job, JobApplication, ResumeProfile


def _job(**kwargs):
    defaults = {
        "naukri_job_id": "12345",
        "title": "Senior Engineer",
        "company": "Acme",
        "url": "https://www.naukri.com/dev-jobs-12345",
    }
    return Job(**{**defaults, **kwargs})


class TestJobEntity:
    def test_defaults_are_populated(self):
        job = _job()

        assert job.location == ""
        assert job.openings == 0
        assert job.has_company_logo is False
        assert job.id is None
        assert job.scraped_at is not None

    def test_skills_are_split_and_trimmed(self):
        job = _job(skills="Python, Docker , ,Kubernetes")

        assert job.get_skills_list() == ["Python", "Docker", "Kubernetes"]

    def test_empty_skills_yield_empty_list(self):
        assert _job(skills="").get_skills_list() == []

    def test_whitespace_only_skills_yield_empty_list(self):
        assert _job(skills="  ,  , ").get_skills_list() == []


class TestJobApplicationEntity:
    def test_defaults(self):
        app = JobApplication()

        assert app.match_score == 0.0
        assert app.should_apply is False
        assert app.applied_at is not None

    def test_matching_skills_list(self):
        assert JobApplication(matching_skills="a, b ,c").get_matching_skills_list() == ["a", "b", "c"]

    def test_empty_matching_skills(self):
        assert JobApplication().get_matching_skills_list() == []

    def test_missing_skills_list(self):
        assert JobApplication(missing_skills="x, y").get_missing_skills_list() == ["x", "y"]

    def test_empty_missing_skills(self):
        assert JobApplication().get_missing_skills_list() == []


class TestResumeProfileEntity:
    def test_mutable_defaults_are_not_shared(self):
        a = ResumeProfile()
        b = ResumeProfile()
        a.skills.append("Python")

        assert b.skills == []

    def test_defaults(self):
        profile = ResumeProfile()

        assert profile.total_experience_years == 0.0
        assert profile.technical_skills == []
        assert profile.file_hash == ""


class TestOrmReprs:
    def test_job_repr(self):
        job = schema.Job(id=1, title="Dev", company="Acme")

        assert repr(job) == "<Job(id=1, title='Dev', company='Acme')>"

    def test_application_repr(self):
        app = schema.Application(id=2, job_id=1, status="applied")

        assert repr(app) == "<Application(id=2, job_id=1, status='applied'>"

    def test_resume_profile_repr_truncates_hash(self):
        profile = schema.ResumeProfile(id=3, file_hash="a" * 64)

        assert repr(profile) == "<ResumeProfile(id=3, file_hash='aaaaaaaa...')>"

    def test_run_log_repr(self):
        run = schema.RunLog(id=4, status="completed", jobs_applied=5, jobs_skipped=2)

        assert repr(run) == "<RunLog(id=4, status='completed', applied=5, skipped=2)>"

    def test_naukri_account_repr(self):
        account = schema.NaukriAccount(id=5, email="a@b.com", is_active=True)

        assert repr(account) == "<NaukriAccount(id=5, email='a@b.com', active=True)>"

    def test_webhook_repr(self):
        hook = schema.Webhook(id=6, name="ops", is_active=False)

        assert repr(hook) == "<Webhook(id=6, name='ops', active=False)>"

    def test_notification_log_repr(self):
        log = schema.NotificationLog(id=7, event="application.created", channel="email")

        assert repr(log) == "<NotificationLog(id=7, event='application.created', channel='email')>"


class TestRunMigrations:
    """The migration helper must be idempotent and add only missing columns."""

    def _legacy_db(self, tmp_path):
        """Build a DB whose tables predate the newer columns."""
        path = tmp_path / "legacy.db"
        engine = create_engine(f"sqlite:///{path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE applications (id INTEGER PRIMARY KEY, job_id INTEGER, "
                    "match_score REAL, match_reasoning TEXT, matching_skills TEXT, "
                    "missing_skills TEXT, status VARCHAR(50), error_message TEXT, applied_at DATETIME)"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title VARCHAR(255), "
                    "company VARCHAR(255), url VARCHAR(1000), location VARCHAR(255), "
                    "experience VARCHAR(100), salary VARCHAR(100), description TEXT, "
                    "skills TEXT, posted_date VARCHAR(100), openings INTEGER, "
                    "has_company_logo BOOLEAN, scraped_at DATETIME)"
                )
            )
        return engine

    def _columns(self, engine, table):
        with engine.connect() as conn:
            return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}

    def test_adds_all_missing_columns(self, tmp_path):
        engine = self._legacy_db(tmp_path)

        with engine.begin() as conn:
            schema._run_migrations(conn)

        apps = self._columns(engine, "applications")
        jobs = self._columns(engine, "jobs")
        assert {"retry_count", "max_retries", "last_retry_at", "source"} <= apps
        assert {"naukri_status", "status_last_synced", "source"} <= jobs

    def test_is_idempotent(self, tmp_path):
        engine = self._legacy_db(tmp_path)

        with engine.begin() as conn:
            schema._run_migrations(conn)
            schema._run_migrations(conn)  # second pass must be a no-op

        assert "retry_count" in self._columns(engine, "applications")

    def test_preserves_existing_rows(self, tmp_path):
        engine = self._legacy_db(tmp_path)
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO applications (id, job_id, status) VALUES (1, 7, 'applied')")
            )

        with engine.begin() as conn:
            schema._run_migrations(conn)

        with engine.connect() as conn:
            row = conn.execute(text("SELECT id, job_id, status FROM applications")).fetchone()

        assert tuple(row) == (1, 7, "applied")

    def test_defaults_are_applied_to_new_columns(self, tmp_path):
        engine = self._legacy_db(tmp_path)

        with engine.begin() as conn:
            schema._run_migrations(conn)
            conn.execute(text("INSERT INTO applications (id, job_id, status) VALUES (2, 8, 'failed')"))

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT retry_count, max_retries, source FROM applications WHERE id=2")
            ).fetchone()

        assert tuple(row) == (0, 3, "naukri")


@pytest.mark.parametrize("table", ["jobs", "applications", "run_logs", "naukri_accounts", "webhooks", "notification_logs"])
def test_every_table_has_a_primary_key(table):
    assert schema.Base.metadata.tables[table].primary_key.columns
