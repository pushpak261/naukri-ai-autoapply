"""
Tests for the database layer.

Tests the SQLAlchemyRepository CRUD operations using a temporary,
file-based SQLite database (one per test, via pytest's tmp_path fixture).
"""

import json

import pytest
import pytest_asyncio

from src.config.constants import ApplicationStatus
from src.database.models import init_db
from src.database.repository import SQLAlchemyRepository


@pytest_asyncio.fixture
async def repo(tmp_path):
    """Create a repository backed by a fresh on-disk SQLite database."""
    db_path = tmp_path / "test.db"
    session_factory = await init_db(db_path)
    repository = SQLAlchemyRepository(session_factory)
    await repository.initialize()
    return repository


class TestJobOperations:
    """Tests for job CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_job(self, repo):
        """Test saving a new job."""
        job = await repo.save_job(
            naukri_job_id="JOB123",
            title="Python Developer",
            company="Test Corp",
            url="https://naukri.com/job/123",
            location="Bangalore",
            experience="3-5 years",
            salary="10-15 LPA",
        )
        assert job.id is not None
        assert job.title == "Python Developer"
        assert job.company == "Test Corp"

    @pytest.mark.asyncio
    async def test_save_duplicate_job(self, repo):
        """Test that saving a duplicate job returns the existing record."""
        job1 = await repo.save_job(
            naukri_job_id="JOB123",
            title="Python Developer",
            company="Test Corp",
            url="https://naukri.com/job/123",
        )
        job2 = await repo.save_job(
            naukri_job_id="JOB123",
            title="Python Developer Updated",
            company="Test Corp",
            url="https://naukri.com/job/123",
        )
        assert job1.id == job2.id



class TestApplicationOperations:
    """Tests for application CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_application(self, repo):
        """Test recording an application."""
        job = await repo.save_job(
            naukri_job_id="JOB789",
            title="FastAPI Developer",
            company="API Corp",
            url="https://naukri.com/job/789",
        )
        app = await repo.save_application(
            job_id=job.id,
            match_score=85.5,
            status=ApplicationStatus.APPLIED,
            match_reasoning="Strong Python match",
            matching_skills="Python, FastAPI",
            missing_skills="Kubernetes",
        )
        assert app.id is not None
        assert app.match_score == 85.5
        assert app.status == ApplicationStatus.APPLIED

    @pytest.mark.asyncio
    async def test_is_already_applied(self, repo):
        """Test checking if a job has been applied to (O(1) in-memory cache)."""
        job = await repo.save_job(
            naukri_job_id="JOB_APPLIED",
            title="Test Job",
            company="Test Corp",
            url="https://naukri.com/job/applied",
        )
        assert repo.is_already_applied("JOB_APPLIED") is False

        await repo.save_application(
            job_id=job.id,
            match_score=80,
            status=ApplicationStatus.APPLIED,
        )
        assert repo.is_already_applied("JOB_APPLIED") is True

    @pytest.mark.asyncio
    async def test_is_already_applied_unknown_job(self, repo):
        """Test checking application status for a non-existent job."""
        assert repo.is_already_applied("UNKNOWN_JOB") is False

    @pytest.mark.asyncio
    async def test_application_stats(self, repo):
        """Test getting application statistics."""
        job1 = await repo.save_job(naukri_job_id="S1", title="J1", company="C1", url="u1")
        job2 = await repo.save_job(naukri_job_id="S2", title="J2", company="C2", url="u2")
        job3 = await repo.save_job(naukri_job_id="S3", title="J3", company="C3", url="u3")

        await repo.save_application(
            job_id=job1.id, match_score=90, status=ApplicationStatus.APPLIED
        )
        await repo.save_application(
            job_id=job2.id, match_score=50, status=ApplicationStatus.SKIPPED_LOW_SCORE
        )
        await repo.save_application(job_id=job3.id, match_score=0, status=ApplicationStatus.FAILED)

        stats = await repo.get_application_stats(days=7)
        assert stats["total"] == 3
        assert stats["applied"] == 1
        assert stats["skipped"] == 1
        assert stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_recent_applications(self, repo):
        """Test getting recent applications with joined job details."""
        job = await repo.save_job(
            naukri_job_id="RECENT1",
            title="Recent Job",
            company="Recent Corp",
            url="https://naukri.com/recent",
            location="Remote",
        )
        await repo.save_application(
            job_id=job.id,
            match_score=88,
            status=ApplicationStatus.APPLIED,
        )

        recent = await repo.get_recent_applications(limit=5)
        assert len(recent) >= 1
        assert recent[0]["job_title"] == "Recent Job"
        assert recent[0]["company"] == "Recent Corp"
        assert recent[0]["match_score"] == 88


class TestResumeProfileOperations:
    """Tests for resume profile caching."""

    @pytest.mark.asyncio
    async def test_save_and_get_profile(self, repo):
        """Test saving and retrieving a resume profile."""
        profile = {"name": "Test User", "skills": ["Python"]}
        await repo.save_resume_profile(
            file_hash="abc123",
            file_path="/test/resume.pdf",
            parsed_json=json.dumps(profile),
        )

        cached = await repo.get_cached_profile("abc123")
        assert cached is not None
        assert cached["name"] == "Test User"
        assert "Python" in cached["skills"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_profile(self, repo):
        """Test retrieving a profile that hasn't been cached."""
        result = await repo.get_cached_profile("nonexistent_hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_existing_profile(self, repo):
        """Test updating an existing cached profile."""
        profile_v1 = {"name": "User V1", "skills": ["Python"]}
        await repo.save_resume_profile(
            file_hash="update_hash",
            file_path="/test/resume.pdf",
            parsed_json=json.dumps(profile_v1),
        )

        profile_v2 = {"name": "User V2", "skills": ["Python", "Django"]}
        await repo.save_resume_profile(
            file_hash="update_hash",
            file_path="/test/resume.pdf",
            parsed_json=json.dumps(profile_v2),
        )

        cached = await repo.get_cached_profile("update_hash")
        assert cached["name"] == "User V2"
        assert "Django" in cached["skills"]


class TestRunLogOperations:
    """Tests for run log tracking."""

    @pytest.mark.asyncio
    async def test_create_run_log(self, repo):
        """Test creating a run log."""
        run_id = await repo.create_run_log(["Python Developer", "Backend Engineer"])
        assert run_id is not None
        assert run_id > 0

    @pytest.mark.asyncio
    async def test_update_run_log(self, repo):
        """Test updating a run log with results."""
        run_id = await repo.create_run_log(["Test"])
        await repo.update_run_log(
            run_log_id=run_id,
            jobs_found=50,
            jobs_applied=10,
            jobs_skipped=35,
            jobs_failed=5,
            status="completed",
        )

        runs = await repo.get_run_stats(limit=1)
        assert len(runs) >= 1
        assert runs[0]["found"] == 50
        assert runs[0]["applied"] == 10
        assert runs[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_stats(self, repo):
        """Test getting run statistics."""
        await repo.create_run_log(["Run 1"])
        await repo.create_run_log(["Run 2"])

        stats = await repo.get_run_stats(limit=10)
        assert len(stats) >= 2
