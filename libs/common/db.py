"""
Shared database helpers for all microservices.

A single database instance is shared across services (per the chosen
"single shared DB" topology). The engine URL is taken from ``DATABASE_URL``;
when unset we fall back to the project's local SQLite file so the system
still runs with zero infrastructure for local development and CI.

Postgres (docker-compose / production):
  * the pool is sized/recycled from environment variables,
  * schema is managed by Alembic when available, with a ``create_all``
    fallback so the system always boots.
SQLite (local/CI):
  * reuse the existing setup (WAL mode, migrations, startup backup).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.naukri_agent.config.settings import PROJECT_ROOT
from src.naukri_agent.database.manager import DatabaseManager
from src.naukri_agent.models.db_schema import Base

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Return the SQLAlchemy URL to use, honouring ``DATABASE_URL``."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    path = PROJECT_ROOT / "data" / "naukri_agent.db"
    return f"sqlite+aiosqlite:///{path}"


def _pool_settings() -> dict:
    """Env-driven pool tuning for Postgres (ignored by SQLite async engine)."""
    return {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True,
    }


async def _migrate_or_create(engine: AsyncEngine, url: str) -> None:
    """Apply Alembic migrations if available, else bootstrap via ``create_all``."""
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        ini = PROJECT_ROOT / "alembic.ini"
        if ini.exists():
            cfg = AlembicConfig(str(ini))
            cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
            cfg.set_main_option("sqlalchemy.url", url)
            command.upgrade(cfg, "head")
            return
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Alembic migration unavailable (%s); using create_all", exc)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_database_manager() -> DatabaseManager:
    """
    Build a ``DatabaseManager`` for the shared DB.

    SQLite (local/CI): reuse the existing setup so WAL mode, migrations and
    the startup backup behaviour are preserved.
    Postgres (docker-compose): create a tuned async engine and ensure tables
    exist (via Alembic when available).
    """
    url = get_database_url()
    if url.startswith("sqlite"):
        from src.naukri_agent.models.db_schema import setup_database_manager

        sqlite_path = Path(url.split("///", 1)[1]) if "///" in url else Path(url)
        return await setup_database_manager(sqlite_path)

    # Normalize to the asyncpg driver so async SQLAlchemy can use the URL.
    if url.startswith("postgresql+asyncpg"):
        pass
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]

    engine: AsyncEngine = create_async_engine(url, future=True, **_pool_settings())
    await _migrate_or_create(engine, url)
    return DatabaseManager(engine=engine)


def is_postgres() -> bool:
    return get_database_url().startswith("postgresql")
