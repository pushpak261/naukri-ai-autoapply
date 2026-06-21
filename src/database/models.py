"""
SQLAlchemy ORM models for the Naukri Agent.

Tracks jobs found, applications submitted, resume profiles, and run logs.
Uses SQLite for zero-configuration, file-based persistence.

Models use SQLAlchemy 2.0's typed declarative style (`Mapped[]` /
`mapped_column()`) rather than legacy `Column()` attributes. This is purely
a typing-layer improvement — it changes no runtime behavior — but it lets
mypy (and your editor) understand that `job.title` is a `str`, not a
`Column[str]`, which eliminates a large class of false-positive type errors
throughout the repository layer.
"""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


class Job(Base):
    """A job listing scraped from Naukri.com."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    naukri_job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str] = mapped_column(String(300), default="")
    experience: Mapped[str] = mapped_column(String(100), default="")
    salary: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[str] = mapped_column(Text, default="")  # Comma-separated skill tags
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    posted_date: Mapped[str] = mapped_column(String(100), default="")
    scraped_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)

    # Relationship
    applications: Mapped[list[Application]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_jobs_company", "company"),
        Index("idx_jobs_scraped_at", "scraped_at"),
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', company='{self.company}')>"


class Application(Base):
    """An application attempt for a specific job."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    match_score: Mapped[float] = mapped_column(default=0.0)
    match_reasoning: Mapped[str] = mapped_column(Text, default="")
    matching_skills: Mapped[str] = mapped_column(Text, default="")  # Comma-separated
    missing_skills: Mapped[str] = mapped_column(Text, default="")  # Comma-separated
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)

    # Relationship
    job: Mapped[Job] = relationship(back_populates="applications")

    __table_args__ = (
        Index("idx_applications_status", "status"),
        Index("idx_applications_applied_at", "applied_at"),
    )

    def __repr__(self) -> str:
        return f"<Application(id={self.id}, job_id={self.job_id}, status='{self.status}')>"


class ResumeProfile(Base):
    """Cached parsed resume profile to avoid repeated AI calls."""

    __tablename__ = "resume_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    parsed_json: Mapped[str] = mapped_column(Text, nullable=False)  # Full JSON of parsed profile
    parsed_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self) -> str:
        return f"<ResumeProfile(id={self.id}, file_hash='{self.file_hash[:8]}...')>"


class RunLog(Base):
    """Log entry for each agent run session."""

    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    search_keywords: Mapped[str] = mapped_column(Text, default="")  # Comma-separated
    jobs_found: Mapped[int] = mapped_column(default=0)
    jobs_applied: Mapped[int] = mapped_column(default=0)
    jobs_skipped: Mapped[int] = mapped_column(default=0)
    jobs_failed: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(
        String(50), default="running"
    )  # running, completed, error, interrupted
    error_message: Mapped[str] = mapped_column(Text, default="")

    def __repr__(self) -> str:
        return (
            f"<RunLog(id={self.id}, status='{self.status}', "
            f"applied={self.jobs_applied}, skipped={self.jobs_skipped})>"
        )


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------
async def init_db(db_path: Path) -> async_sessionmaker[AsyncSession]:
    """
    Initialize the SQLite database and return an AsyncSession factory.

    Creates all tables if they don't exist. This is idempotent.

    Note: this function is intentionally side-effect-free with respect to
    module/global state — it returns a fresh session factory bound to a new
    engine every time it's called. Callers (see DependencyFactory) are
    responsible for holding onto the returned factory and passing it to
    whatever needs it. This avoids the pitfalls of a shared mutable module
    global (which breaks under concurrent test runs or multiple agent
    instances in the same process).

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A SQLAlchemy async_sessionmaker bound to the async engine.
    """
    from src.database.backup import backup_database

    backup_database(db_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Run sync schema creation inside async context
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return async_sessionmaker(bind=engine, expire_on_commit=False)
