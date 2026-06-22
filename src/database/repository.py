"""
Data access layer for the Naukri Agent.

Provides high-level CRUD operations over the SQLAlchemy models,
encapsulating all database interactions behind a clean interface.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.core.interfaces import IRepository
from src.database.models import Job, Application, ResumeProfile, RunLog


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

    async def initialize(self) -> None:
        """Load all applied job IDs into an O(1) hash set for fast deduplication."""
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(Job.naukri_job_id).join(Application, Application.job_id == Job.id)
                )
                applied_job_ids = result.scalars().all()
                for naukri_job_id in applied_job_ids:
                    if naukri_job_id:
                        self._applied_jobs_cache.add(naukri_job_id)
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
            result = await session.execute(select(Job).filter(Job.naukri_job_id == naukri_job_id))
            existing = result.scalar_one_or_none()

            if existing:
                # Update description if it was previously empty
                if description and not existing.description:
                    existing.description = description
                return existing

            job = Job(
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
            session.add(job)
            await session.flush()
            # To return the job without expiring attributes
            await session.refresh(job)
            return job

    def is_already_applied(self, naukri_job_id: str) -> bool:
        """Check if we've already applied to this job (any status) using O(1) cache."""
        return naukri_job_id in self._applied_jobs_cache

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
    ) -> Application:
        """Record an application attempt."""
        async with self._session_factory() as session, session.begin():
            app = Application(
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
            job_result = await session.execute(select(Job).filter(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if job and job.naukri_job_id:
                self._applied_jobs_cache.add(job.naukri_job_id)

            return app

    async def get_today_application_count(self) -> int:
        """Count applications made today (UTC)."""
        async with self._session_factory() as session:
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            from src.config.constants import ApplicationStatus

            result = await session.execute(
                select(func.count(Application.id)).filter(
                    Application.applied_at >= today_start,
                    Application.status == ApplicationStatus.APPLIED,
                )
            )
            return result.scalar_one() or 0

    async def get_application_stats(self, days: int = 7) -> dict[str, int]:
        """Get application statistics for the last N days."""
        async with self._session_factory() as session:
            since = datetime.now(UTC) - timedelta(days=days)
            result = await session.execute(
                select(Application).filter(Application.applied_at >= since)
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
                select(Application, Job)
                .join(Job, Application.job_id == Job.id)
                .order_by(Application.applied_at.desc())
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
                select(ResumeProfile).filter(ResumeProfile.file_hash == file_hash)
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
                return existing

            profile = ResumeProfile(
                file_hash=file_hash,
                file_path=file_path,
                parsed_json=parsed_json,
            )
            session.add(profile)
            await session.flush()
            await session.refresh(profile)
            return profile

    async def get_cached_profile(self, file_hash: str) -> dict | None:
        """
        Retrieve a cached resume profile by file hash.

        Returns the parsed JSON as a dict, or None if not cached.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(ResumeProfile).filter(ResumeProfile.file_hash == file_hash)
            )
            profile = result.scalar_one_or_none()
            if profile:
                return json.loads(profile.parsed_json)
            return None

    # -----------------------------------------------------------------------
    # Run log operations
    # -----------------------------------------------------------------------
    async def create_run_log(self, search_keywords: list[str]) -> int:
        """Create a new run log entry. Returns the run log ID."""
        async with self._session_factory() as session, session.begin():
            run_log = RunLog(
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
            result = await session.execute(select(RunLog).filter(RunLog.id == run_log_id))
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
                select(RunLog).order_by(RunLog.started_at.desc()).limit(limit)
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
