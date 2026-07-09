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

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.naukri_agent.database.manager import DatabaseManager

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    skills: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    posted_date: Mapped[str] = mapped_column(String(100), default="")
    openings: Mapped[int] = mapped_column(default=0)
    has_company_logo: Mapped[bool] = mapped_column(default=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    naukri_status: Mapped[str] = mapped_column(String(50), default="")
    status_last_synced: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
        Index("idx_applications_status", "status"),
        Index("idx_applications_applied_at", "applied_at"),
    )

    def __repr__(self) -> str:
        return f"<Application(id={self.id}, job_id={self.job_id}, status='{self.status}'>"


class ResumeProfile(Base):
    """Cached parsed resume profile to avoid repeated AI calls."""

    __tablename__ = "resume_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    parsed_json: Mapped[str] = mapped_column(Text, nullable=False)  # Full JSON of parsed profile
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ResumeProfile(id={self.id}, file_hash='{self.file_hash[:8]}...')>"


class AppConfig(Base):
    """User-editable configuration overrides (dashboard / API changes)."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AppConfig(key='{self.key}')>"


class RunLog(Base):
    """Log entry for each agent run session."""

    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class NaukriAccount(Base):
    """Multiple Naukri.com account profiles."""

    __tablename__ = "naukri_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(default=False)
    is_primary: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_data: Mapped[str] = mapped_column(Text, default="")

    def __repr__(self) -> str:
        return f"<NaukriAccount(id={self.id}, email='{self.email}', active={self.is_active})>"


class Webhook(Base):
    """Webhook configuration for external service notifications."""

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    secret: Mapped[str] = mapped_column(String(500), default="")
    events: Mapped[str] = mapped_column(
        Text, default="application.created,application.failed,run.completed"
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_count: Mapped[int] = mapped_column(default=0)

    def __repr__(self) -> str:
        return f"<Webhook(id={self.id}, name='{self.name}', active={self.is_active})>"


class ScreeningQuestion(Base):
    """Screening question cache and failed-question queue for manual answers."""

    __tablename__ = "screening_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_type: Mapped[str] = mapped_column(String(50), default="text")
    options_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source: Mapped[str] = mapped_column(String(20), default="")
    failure_count: Mapped[int] = mapped_column(default=0)
    last_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    last_application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ScreeningQuestion(id={self.id}, status='{self.status}')>"


class NotificationLog(Base):
    """Log of all sent notifications (email, webhook)."""

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    recipient: Mapped[str] = mapped_column(String(500), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(50), default="sent")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<NotificationLog(id={self.id}, event='{self.event}', channel='{self.channel}')>"


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------
def _column_default_sql(column) -> str:
    """Render a SQLite DEFAULT clause for a new column, if one is defined."""
    if column.server_default is not None:
        return f" DEFAULT {column.server_default.arg}"

    if column.default is None:
        return ""

    default_arg = column.default.arg
    if callable(default_arg):
        return ""

    if isinstance(default_arg, bool):
        return f" DEFAULT {int(default_arg)}"
    if isinstance(default_arg, str):
        return f" DEFAULT '{default_arg}'"
    return f" DEFAULT {default_arg}"


def _sync_sqlite_schema(sync_conn) -> None:
    """Add ORM columns that are missing from existing SQLite tables."""
    inspector = inspect(sync_conn)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(sync_conn.dialect)
            default_sql = _column_default_sql(column)
            sync_conn.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {column.name} {col_type}{default_sql}"
                )
            )


async def setup_database_manager(db_path: Path) -> "DatabaseManager":
    """
    Initialize the SQLite engine and return a DatabaseManager.
    """
    from src.naukri_agent.utils.logger import log_info
    from src.naukri_agent.database.manager import DatabaseManager
    from src.naukri_agent.database.backup import DatabaseBackupService

    # Backup existing database before initialization
    backup_service = DatabaseBackupService(db_path)
    backup_service.backup()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Enable WAL mode for concurrent read/write safety
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.commit()

    # Sync schema for SQLite (create tables, then add any missing columns)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_sqlite_schema)

    log_info(f"Using local SQLite database at {db_path}.")

    return DatabaseManager(engine=engine)
