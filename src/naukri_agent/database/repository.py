"""
Data access layer for the Naukri Agent.

Provides high-level CRUD operations over the SQLAlchemy models,
encapsulating all database interactions behind a clean interface.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.naukri_agent.core.domain.entities import Job, JobApplication, ResumeProfile
from src.naukri_agent.core.interfaces import IRepository
from src.naukri_agent.database.models import (
    Application as DBApplication,
)
from src.naukri_agent.database.models import (
    Job as DBJob,
)
from src.naukri_agent.database.models import (
    ResumeProfile as DBResumeProfile,
)
from src.naukri_agent.database.models import (
    RunLog as DBRunLog,
)


def _map_db_to_resume_profile(data: dict, file_hash: str) -> ResumeProfile:
    education = data.get("education", [])
    if education and not isinstance(education[0], dict):
        education = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in education]
    work_experience = data.get("work_experience", [])
    if work_experience and not isinstance(work_experience[0], dict):
        work_experience = [
            w.model_dump() if hasattr(w, "model_dump") else dict(w) for w in work_experience
        ]

    return ResumeProfile(
        name=data.get("name", ""),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        current_title=data.get("current_title", ""),
        summary=data.get("summary", ""),
        total_experience_years=float(data.get("total_experience_years", 0.0) or 0.0),
        skills=data.get("skills", []),
        technical_skills=data.get("technical_skills", []),
        soft_skills=data.get("soft_skills", []),
        job_titles_held=data.get("job_titles_held", []),
        education=education,
        work_experience=work_experience,
        certifications=data.get("certifications", []),
        languages=data.get("languages", []),
        key_achievements=data.get("key_achievements", []),
        file_hash=file_hash,
    )


class SQLAlchemyRepository(IRepository):
    """
    SQLAlchemy implementation of the IRepository interface.

    Usage:
        repo = SQLAlchemyRepository(session_factory)
        await repo.initialize()
        await repo.save_job(naukri_job_id="...", title="...", ...)
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._applied_jobs_cache: set[str] = set()
        self._applied_composite_cache: set[tuple[str, str]] = set()

    async def initialize(self) -> None:
        """Load all applied job IDs and (title, company) combinations into O(1) hash sets for fast deduplication."""
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(DBJob.naukri_job_id, DBJob.title, DBJob.company).join(
                        DBApplication, DBApplication.job_id == DBJob.id
                    )
                )
                rows = result.all()
                for naukri_job_id, title, company in rows:
                    if naukri_job_id:
                        self._applied_jobs_cache.add(naukri_job_id)
                    if title and company:
                        self._applied_composite_cache.add(
                            (title.lower().strip(), company.lower().strip())
                        )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Failed to load cache: {e}")

    # -----------------------------------------------------------------------
    # Job operations
    # -----------------------------------------------------------------------
    async def save_job(
        self,
        naukri_job_id: str,
        title: str,
        company: str,
        url: str,
        location: str = "",
        experience: str = "",
        salary: str = "",
        description: str = "",
        skills: str = "",
        posted_date: str = "",
    ) -> Job:
        """Save a job listing. Returns existing if already saved."""
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(DBJob).filter(DBJob.naukri_job_id == naukri_job_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update description if it was previously empty
                if description and not existing.description:
                    existing.description = description
                db_job = existing
            else:
                db_job = DBJob(
                    naukri_job_id=naukri_job_id,
                    title=title,
                    company=company,
                    url=url,
                    location=location,
                    experience=experience,
                    salary=salary,
                    description=description,
                    skills=skills,
                    posted_date=posted_date,
                )
                session.add(db_job)
                await session.flush()
                # To return the job without expiring attributes
                await session.refresh(db_job)

            return Job(
                id=db_job.id,
                naukri_job_id=db_job.naukri_job_id,
                title=db_job.title,
                company=db_job.company,
                url=db_job.url,
                location=db_job.location,
                experience=db_job.experience,
                salary=db_job.salary,
                description=db_job.description,
                skills=db_job.skills,
                posted_date=db_job.posted_date,
                scraped_at=db_job.scraped_at,
            )

    def is_already_applied(self, naukri_job_id: str) -> bool:
        """Check if we've already applied to this job (any status) using O(1) cache."""
        return naukri_job_id in self._applied_jobs_cache

    def is_already_applied_composite(self, title: str, company: str) -> bool:
        """Check if we've already applied to this job title & company combination (O(1))."""
        if not title or not company:
            return False
        return (title.lower().strip(), company.lower().strip()) in self._applied_composite_cache

    # -----------------------------------------------------------------------
    # Application operations
    # -----------------------------------------------------------------------
    async def save_application(
        self,
        job_id: int,
        match_score: float,
        status: str,
        match_reasoning: str = "",
        matching_skills: str = "",
        missing_skills: str = "",
        error_message: str = "",
    ) -> JobApplication:
        """Record an application attempt."""
        async with self._session_factory() as session, session.begin():
            app = DBApplication(
                job_id=job_id,
                match_score=match_score,
                match_reasoning=match_reasoning,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                status=status,
                error_message=error_message,
            )
            session.add(app)
            await session.flush()
            await session.refresh(app)

            # Update O(1) cache
            job_result = await session.execute(select(DBJob).filter(DBJob.id == job_id))
            job = job_result.scalar_one_or_none()
            if job:
                if job.naukri_job_id:
                    self._applied_jobs_cache.add(job.naukri_job_id)
                if job.title and job.company:
                    self._applied_composite_cache.add(
                        (job.title.lower().strip(), job.company.lower().strip())
                    )

            return JobApplication(
                id=app.id,
                job_id=app.job_id,
                match_score=app.match_score,
                status=app.status,
                match_reasoning=app.match_reasoning,
                matching_skills=app.matching_skills,
                missing_skills=app.missing_skills,
                error_message=app.error_message,
                applied_at=app.applied_at,
            )

    async def get_today_application_count(self) -> int:
        """Count applications made today (UTC)."""
        async with self._session_factory() as session:
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            from src.naukri_agent.config.constants import ApplicationStatus

            result = await session.execute(
                select(func.count(DBApplication.id)).filter(
                    DBApplication.applied_at >= today_start,
                    DBApplication.status == ApplicationStatus.APPLIED,
                )
            )
            return result.scalar_one() or 0

    async def get_application_stats(self, days: int = 7) -> dict[str, int]:
        """Get application statistics for the last N days."""
        async with self._session_factory() as session:
            since = datetime.now(UTC) - timedelta(days=days)
            result = await session.execute(
                select(DBApplication).filter(DBApplication.applied_at >= since)
            )
            apps = result.scalars().all()
            stats: dict[str, int] = {
                "total": len(apps),
                "applied": 0,
                "skipped": 0,
                "failed": 0,
            }
            for app in apps:
                if app.status == "applied":
                    stats["applied"] += 1
                elif app.status.startswith("skipped"):
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1
            return stats

    async def get_recent_applications(self, limit: int = 20) -> list[dict]:
        """Get the most recent application records with job details."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(DBApplication, DBJob)
                .join(DBJob, DBApplication.job_id == DBJob.id)
                .order_by(DBApplication.applied_at.desc())
                .limit(limit)
            )
            results = result.all()
            return [
                {
                    "job_title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "match_score": app.match_score,
                    "status": app.status,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else "",
                    "url": job.url,
                    "error_message": app.error_message or "",
                }
                for app, job in results
            ]

    # -----------------------------------------------------------------------
    # Resume profile operations
    # -----------------------------------------------------------------------
    async def save_resume_profile(
        self, file_hash: str, file_path: str, parsed_json: str
    ) -> ResumeProfile:
        """Save or update a parsed resume profile."""
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(DBResumeProfile).filter(DBResumeProfile.file_hash == file_hash)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.parsed_json = parsed_json
                existing.parsed_at = datetime.now(UTC)
                # NOTE: do NOT call session.refresh(existing) here. refresh()
                # re-loads attributes from the database, which discards the
                # in-memory mutation we just made *before* it's flushed —
                # the update would silently never reach the DB. Since the
                # session factory uses expire_on_commit=False, the object
                # we already mutated is exactly what callers should see.
                db_profile = existing
            else:
                db_profile = DBResumeProfile(
                    file_hash=file_hash,
                    file_path=file_path,
                    parsed_json=parsed_json,
                )
                session.add(db_profile)
                await session.flush()
                await session.refresh(db_profile)

            profile_data = json.loads(db_profile.parsed_json)
            return _map_db_to_resume_profile(profile_data, db_profile.file_hash)

    async def get_cached_profile(self, file_hash: str) -> ResumeProfile | None:
        """
        Retrieve a cached resume profile by file hash.

        Returns the parsed domain ResumeProfile, or None if not cached.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(DBResumeProfile).filter(DBResumeProfile.file_hash == file_hash)
            )
            profile = result.scalar_one_or_none()
            if profile:
                profile_data = json.loads(profile.parsed_json)
                return _map_db_to_resume_profile(profile_data, profile.file_hash)
            return None

    # -----------------------------------------------------------------------
    # Run log operations
    # -----------------------------------------------------------------------
    async def create_run_log(self, search_keywords: list[str]) -> int:
        """Create a new run log entry. Returns the run log ID."""
        async with self._session_factory() as session, session.begin():
            run_log = DBRunLog(
                search_keywords=", ".join(search_keywords),
                status="running",
            )
            session.add(run_log)
            await session.flush()
            await session.refresh(run_log)
            return run_log.id

    async def update_run_log(
        self,
        run_log_id: int,
        jobs_found: int = 0,
        jobs_applied: int = 0,
        jobs_skipped: int = 0,
        jobs_failed: int = 0,
        status: str = "completed",
        error_message: str = "",
    ) -> None:
        """Update a run log entry with final statistics."""
        async with self._session_factory() as session, session.begin():
            result = await session.execute(select(DBRunLog).filter(DBRunLog.id == run_log_id))
            run_log = result.scalar_one_or_none()
            if run_log:
                run_log.ended_at = datetime.now(UTC)
                run_log.jobs_found = jobs_found
                run_log.jobs_applied = jobs_applied
                run_log.jobs_skipped = jobs_skipped
                run_log.jobs_failed = jobs_failed
                run_log.status = status
                run_log.error_message = error_message

    async def get_run_stats(self, limit: int = 10) -> list[dict]:
        """Get the most recent run logs."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(DBRunLog).order_by(DBRunLog.started_at.desc()).limit(limit)
            )
            logs = result.scalars().all()
            return [
                {
                    "id": log.id,
                    "started_at": log.started_at.isoformat() if log.started_at else "",
                    "ended_at": log.ended_at.isoformat() if log.ended_at else "",
                    "keywords": log.search_keywords,
                    "found": log.jobs_found,
                    "applied": log.jobs_applied,
                    "skipped": log.jobs_skipped,
                    "failed": log.jobs_failed,
                    "status": log.status,
                }
                for log in logs
            ]

    async def get_all_job_descriptions(self) -> list[str]:
        """Fetch all stored job descriptions to construct a TF-IDF reference corpus."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(DBJob.description).filter(DBJob.description.is_not(None), DBJob.description != "")
            )
            return list(result.scalars().all())
