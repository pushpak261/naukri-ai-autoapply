"""FastAPI dependency injection."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.services.run_manager import RunManager
from src.naukri_agent.config.settings import Settings, get_settings
from src.naukri_agent.database.models import init_db
from src.naukri_agent.database.repository import SQLAlchemyRepository


@lru_cache
def get_run_manager() -> RunManager:
    return RunManager()


def get_app_settings() -> Settings:
    return get_settings()


_session_factory: async_sessionmaker[AsyncSession] | None = None


async def get_repository() -> SQLAlchemyRepository:
    global _session_factory
    if _session_factory is None:
        settings = get_settings()
        _session_factory = await init_db(settings.db_path)
    return SQLAlchemyRepository(_session_factory)
