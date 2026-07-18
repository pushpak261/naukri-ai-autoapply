"""
SQLAlchemy ORM models for the LinkedIn Agent.

Tracks jobs found, applications submitted, resume profiles, and run logs.
Uses SQLite for zero-configuration, file-based persistence.

Models use SQLAlchemy 2.0's typed declarative style (`Mapped[]` /
`mapped_column()`) for type safety throughout the repository layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.linked_agent.database.manager import DatabaseManager

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for LinkedIn agent."""

    pass


class Job(Base):
    """A job listing scraped from LinkedIn."""

    __tablename__ = "linkedin_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    linkedin_job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str] = mapped_column(String(300), default="")
    experience: Mapped[str] = mapped_column(String(100), default="")
    salary: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    posted_date: Mapped[str] = mapped_column(String(100), default="")
    job_type: Mapped[str] = mapped_column(String(50), default="")
    work_type: Mapped[str] = mapped_column(String(50), default="")
    applicant_count: Mapped[int] = mapped_column(default=0)
    easy_apply: Mapped[bool] = mapped_column(default=False)
    company_logo_url: Mapped[str] = mapped_column(String(2000), default="")
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    linkedin_status: Mapped[str] = mapped_column(String(50), default="")

    applications: Mapped[list[Application]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_linkedin_jobs_company", "company"),
        Index("idx_linkedin_jobs_scraped_at", "scraped_at"),
    )

    def __repr__(self) -> str:
        return f"<LinkedInJob(id={self.id}, title='{self.title}', company='{self.company}')>"


class Application(Base):
    """An application attempt for a specific job."""

    __tablename__ = "linkedin_applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("linkedin_jobs.id"), nullable=False, index=True)
    match_score: Mapped[float] = mapped_column(default=0.0)
    match_reasoning: Mapped[str] = mapped_column(Text, default="")
    matching_skills: Mapped[str] = mapped_column(Text, default="")
    missing_skills: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(back_populates="applications")

    __table_args__ = (
        Index("idx_linkedin_applications_status", "status"),
        Index("idx_linkedin_applications_applied_at", "applied_at"),
    )

    def __repr__(self) -> str:
        return f"<LinkedInApplication(id={self.id}, job_id={self.job_id}, status='{self.status}')>"


class ResumeProfile(Base):
    """Cached parsed resume profile to avoid repeated AI calls."""

    __tablename__ = "linkedin_resume_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    parsed_json: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<LinkedInResumeProfile(id={self.id}, file_hash='{self.file_hash[:8]}...')>"


class RunLog(Base):
    """Log entry for each agent run session."""

    __tablename__ = "linkedin_run_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_keywords: Mapped[str] = mapped_column(Text, default="")
    jobs_found: Mapped[int] = mapped_column(default=0)
    jobs_applied: Mapped[int] = mapped_column(default=0)
    jobs_skipped: Mapped[int] = mapped_column(default=0)
    jobs_failed: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(50), default="running")
    error_message: Mapped[str] = mapped_column(Text, default="")

    def __repr__(self) -> str:
        return (
            f"<LinkedInRunLog(id={self.id}, status='{self.status}', "
            f"applied={self.jobs_applied}, skipped={self.jobs_skipped})>"
        )


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------
async def setup_database_manager(db_path: Path) -> "DatabaseManager":
    """Initialize the SQLite engine and return a DatabaseManager."""
    from src.linked_agent.utils.logger import log_info
    from src.linked_agent.database.manager import DatabaseManager

    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.commit()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    log_info(f"LinkedIn agent using SQLite database at {db_path}.")
    return DatabaseManager(engine=engine)
