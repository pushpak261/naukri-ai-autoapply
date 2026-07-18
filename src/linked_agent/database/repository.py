"""
SQLAlchemy repository implementation for the LinkedIn Agent.
Implements the IRepository interface with async SQLite operations.

Optionally writes through to the Naukri DB so the unified frontend can
query LinkedIn data via the same source-filtered endpoints.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.linked_agent.database.manager import DatabaseManager
from src.linked_agent.models.db_schema import (
    Application,
    Job,
    ResumeProfile,
    RunLog,
)
from src.linked_agent.models.entities import Job as DomainJob, JobApplication
from src.linked_agent.utils.logger import get_logger

if TYPE_CHECKING:
    from src.naukri_agent.database.manager import DatabaseManager as NaukriDBManager

logger = get_logger(__name__)


class SQLAlchemyRepository:
    """SQLAlchemy-based repository for LinkedIn agent data persistence."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        naukri_db_manager: "NaukriDBManager | None" = None,
    ) -> None:
        self._db = db_manager
        self._naukri_db = naukri_db_manager
        self._applied_jobs_cache: set[str] = set()
        self._applied_composite_cache: set[tuple[str, str]] = set()
        self._initialized = False

    async def initialize(self) -> None:
        """Load dedup caches from the database — only jobs that were actually applied to."""
        if self._initialized:
            return

        async with self._db.get_session() as session:
            # Load job IDs that have an "applied" application record
            result = await session.execute(
                select(Job.linkedin_job_id)
                .join(Application, Application.job_id == Job.id)
                .where(Application.status == "applied")
            )
            for row in result.scalars():
                self._applied_jobs_cache.add(row)

            # Load title+company composites for applied jobs
            result = await session.execute(
                select(Job.title, Job.company)
                .join(Application, Application.job_id == Job.id)
                .where(Application.status == "applied")
            )
            for row in result:
                self._applied_composite_cache.add((row[0].lower(), row[1].lower()))

        self._initialized = True
        logger.info(
            f"LinkedIn dedup cache loaded: {len(self._applied_jobs_cache)} applied job IDs, "
            f"{len(self._applied_composite_cache)} applied composites"
        )

    # ------------------------------------------------------------------
    # Write-through helpers for the Naukri DB
    # ------------------------------------------------------------------
    async def _write_through_job(
        self,
        linkedin_job_id: str,
        title: str,
        company: str,
        url: str,
        location: str,
        experience: str,
        salary: str,
        description: str,
        skills: str,
        posted_date: str,
        job_type: str,
        work_type: str,
        applicant_count: int,
        easy_apply: bool,
        company_logo_url: str,
    ) -> None:
        """Mirror a LinkedIn job into the Naukri DB with source='linkedin'."""
        if self._naukri_db is None:
            return
        try:
            from src.naukri_agent.models.db_schema import (
                Job as NaukriJob,
            )

            async with self._naukri_db.session_factory() as session:
                existing = await session.execute(
                    select(NaukriJob).where(NaukriJob.naukri_job_id == f"li_{linkedin_job_id}")
                )
                db_job = existing.scalar_one_or_none()
                if db_job:
                    db_job.title = title
                    db_job.company = company
                    db_job.url = url
                    db_job.location = location
                    db_job.experience = experience
                    db_job.salary = salary
                    db_job.description = description
                    db_job.skills = skills
                    db_job.posted_date = posted_date
                    db_job.source = "linkedin"
                else:
                    db_job = NaukriJob(
                        naukri_job_id=f"li_{linkedin_job_id}",
                        title=title,
                        company=company,
                        url=url,
                        location=location,
                        experience=experience,
                        salary=salary,
                        description=description,
                        skills=skills,
                        posted_date=posted_date,
                        source="linkedin",
                    )
                    session.add(db_job)
                await session.commit()
        except Exception as exc:
            logger.warning(f"Write-through job mirror failed: {exc}")

    async def _write_through_application(
        self,
        linkedin_job_id: str,
        match_score: float,
        status: str,
        match_reasoning: str,
        matching_skills: str,
        missing_skills: str,
        error_message: str,
    ) -> None:
        """Mirror a LinkedIn application into the Naukri DB with source='linkedin'."""
        if self._naukri_db is None:
            return
        try:
            from src.naukri_agent.models.db_schema import (
                Job as NaukriJob,
                Application as NaukriApplication,
            )

            async with self._naukri_db.session_factory() as session:
                # Find the mirrored job
                result = await session.execute(
                    select(NaukriJob).where(NaukriJob.naukri_job_id == f"li_{linkedin_job_id}")
                )
                naukri_job = result.scalar_one_or_none()
                if not naukri_job:
                    logger.warning(
                        f"Write-through application skipped: no mirrored job for li_{linkedin_job_id}"
                    )
                    return

                app = NaukriApplication(
                    job_id=naukri_job.id,
                    match_score=match_score,
                    status=status,
                    match_reasoning=match_reasoning,
                    matching_skills=matching_skills,
                    missing_skills=missing_skills,
                    error_message=error_message,
                    source="linkedin",
                )
                session.add(app)
                await session.commit()
        except Exception as exc:
            logger.warning(f"Write-through application mirror failed: {exc}")

    async def save_job(
        self,
        linkedin_job_id: str,
        title: str,
        company: str,
        url: str,
        location: str = "",
        experience: str = "",
        salary: str = "",
        description: str = "",
        skills: str = "",
        posted_date: str = "",
        job_type: str = "",
        work_type: str = "",
        applicant_count: int = 0,
        easy_apply: bool = False,
        company_logo_url: str = "",
    ) -> DomainJob:
        """Save or update a job listing."""
        async with self._db.get_session() as session:
            existing = await session.execute(
                select(Job).where(Job.linkedin_job_id == linkedin_job_id)
            )
            db_job = existing.scalar_one_or_none()

            if db_job:
                db_job.title = title
                db_job.company = company
                db_job.url = url
                db_job.location = location
                db_job.experience = experience
                db_job.salary = salary
                db_job.description = description
                db_job.skills = skills
                db_job.posted_date = posted_date
                db_job.job_type = job_type
                db_job.work_type = work_type
                db_job.applicant_count = applicant_count
                db_job.easy_apply = easy_apply
                db_job.company_logo_url = company_logo_url
            else:
                db_job = Job(
                    linkedin_job_id=linkedin_job_id,
                    title=title,
                    company=company,
                    url=url,
                    location=location,
                    experience=experience,
                    salary=salary,
                    description=description,
                    skills=skills,
                    posted_date=posted_date,
                    job_type=job_type,
                    work_type=work_type,
                    applicant_count=applicant_count,
                    easy_apply=easy_apply,
                    company_logo_url=company_logo_url,
                )
                session.add(db_job)

            await session.flush()

            # NOTE: Do NOT add to dedup cache here. Only save_application with
            # status="applied" should add to the cache, to avoid blocking retries
            # of jobs that were previously skipped (not applied).

            await self._write_through_job(
                linkedin_job_id=linkedin_job_id,
                title=title,
                company=company,
                url=url,
                location=location,
                experience=experience,
                salary=salary,
                description=description,
                skills=skills,
                posted_date=posted_date,
                job_type=job_type,
                work_type=work_type,
                applicant_count=applicant_count,
                easy_apply=easy_apply,
                company_logo_url=company_logo_url,
            )

            return DomainJob(
                linkedin_job_id=linkedin_job_id,
                title=title,
                company=company,
                url=url,
                location=location,
                experience=experience,
                salary=salary,
                description=description,
                skills=skills,
                posted_date=posted_date,
                job_type=job_type,
                work_type=work_type,
                applicant_count=applicant_count,
                easy_apply=easy_apply,
                company_logo_url=company_logo_url,
                id=db_job.id,
            )

    def is_already_applied(self, linkedin_job_id: str) -> bool:
        return linkedin_job_id in self._applied_jobs_cache

    def is_already_applied_composite(self, title: str, company: str) -> bool:
        return (title.lower(), company.lower()) in self._applied_composite_cache

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
        async with self._db.get_session() as session:
            app = Application(
                job_id=job_id,
                match_score=match_score,
                status=status,
                match_reasoning=match_reasoning,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                error_message=error_message,
            )
            session.add(app)
            await session.flush()

            # Look up linkedin_job_id and title+company for write-through and dedup cache
            job_result = await session.execute(
                select(Job.linkedin_job_id, Job.title, Job.company).where(Job.id == job_id)
            )
            job_row = job_result.one_or_none()
            linkedin_job_id = job_row[0] if job_row else ""
            job_title = job_row[1] if job_row else ""
            job_company = job_row[2] if job_row else ""

            # Update dedup cache ONLY for actual applications
            if status == "applied" and linkedin_job_id:
                self._applied_jobs_cache.add(linkedin_job_id)
                if job_title and job_company:
                    self._applied_composite_cache.add((job_title.lower(), job_company.lower()))

            await self._write_through_application(
                linkedin_job_id=linkedin_job_id,
                match_score=match_score,
                status=status,
                match_reasoning=match_reasoning,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                error_message=error_message,
            )

            return JobApplication(
                job_id=job_id,
                match_score=match_score,
                status=status,
                match_reasoning=match_reasoning,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                error_message=error_message,
                id=app.id,
            )

    async def get_today_application_count(self) -> int:
        async with self._db.get_session() as session:
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            result = await session.execute(
                select(func.count(Application.id)).where(
                    Application.status == "applied",
                    Application.applied_at >= today_start,
                )
            )
            return result.scalar() or 0

    async def get_application_stats(self, days: int = 7) -> dict[str, int]:
        async with self._db.get_session() as session:
            from datetime import timedelta
            cutoff = datetime.now(UTC) - timedelta(days=days)

            total = await session.execute(
                select(func.count(Application.id)).where(Application.applied_at >= cutoff)
            )
            applied = await session.execute(
                select(func.count(Application.id)).where(
                    Application.status == "applied", Application.applied_at >= cutoff
                )
            )
            skipped = await session.execute(
                select(func.count(Application.id)).where(
                    Application.status.like("skipped%"), Application.applied_at >= cutoff
                )
            )
            failed = await session.execute(
                select(func.count(Application.id)).where(
                    Application.status.in_(["failed", "error"]),
                    Application.applied_at >= cutoff,
                )
            )

            return {
                "total": total.scalar() or 0,
                "applied": applied.scalar() or 0,
                "skipped": skipped.scalar() or 0,
                "failed": failed.scalar() or 0,
            }

    async def get_recent_applications(self, limit: int = 20) -> list[dict]:
        async with self._db.get_session() as session:
            result = await session.execute(
                select(Application, Job)
                .join(Job, Application.job_id == Job.id)
                .order_by(Application.applied_at.desc())
                .limit(limit)
            )
            rows = result.all()
            return [
                {
                    "job_title": app.Job.title,
                    "company": app.Application.match_reasoning or app.Job.company,
                    "match_score": app.Application.match_score,
                    "status": app.Application.status,
                    "applied_at": (
                        app.Application.applied_at.isoformat() if app.Application.applied_at else ""
                    ),
                }
                for app in rows
            ]

    async def save_resume_profile(
        self, file_hash: str, file_path: str, parsed_json: str
    ) -> ResumeProfile:
        async with self._db.get_session() as session:
            profile = ResumeProfile(
                file_hash=file_hash,
                file_path=file_path,
                parsed_json=parsed_json,
            )
            session.add(profile)
            await session.flush()
            return profile

    async def get_cached_profile(self, file_hash: str) -> ResumeProfile | None:
        async with self._db.get_session() as session:
            result = await session.execute(
                select(ResumeProfile).where(ResumeProfile.file_hash == file_hash)
            )
            return result.scalar_one_or_none()

    async def create_run_log(self, search_keywords: list[str]) -> int:
        async with self._db.get_session() as session:
            log = RunLog(search_keywords=", ".join(search_keywords))
            session.add(log)
            await session.flush()
            return log.id  # type: ignore

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
        async with self._db.get_session() as session:
            result = await session.execute(select(RunLog).where(RunLog.id == run_log_id))
            log = result.scalar_one_or_none()
            if log:
                log.ended_at = datetime.now(UTC)
                log.jobs_found = jobs_found
                log.jobs_applied = jobs_applied
                log.jobs_skipped = jobs_skipped
                log.jobs_failed = jobs_failed
                log.status = status
                log.error_message = error_message

    async def get_run_stats(self, limit: int = 10) -> list[dict]:
        async with self._db.get_session() as session:
            result = await session.execute(
                select(RunLog).order_by(RunLog.started_at.desc()).limit(limit)
            )
            logs = result.scalars().all()
            return [
                {
                    "started_at": log.started_at.isoformat() if log.started_at else "",
                    "keywords": log.search_keywords,
                    "found": log.jobs_found,
                    "applied": log.jobs_applied,
                    "skipped": log.jobs_skipped,
                    "status": log.status,
                }
                for log in logs
            ]

    async def get_all_job_descriptions(self) -> list[str]:
        async with self._db.get_session() as session:
            result = await session.execute(select(Job.description))
            return [row for row in result.scalars() if row]
