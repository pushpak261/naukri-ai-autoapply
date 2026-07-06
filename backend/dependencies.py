"""FastAPI dependency injection."""

from __future__ import annotations

from functools import lru_cache

from backend.services.run_manager import RunManager
from src.naukri_agent.config.settings import Settings, get_settings
from src.naukri_agent.database.manager import DatabaseManager
from src.naukri_agent.database.repository import SQLAlchemyRepository
from src.naukri_agent.models.db_schema import setup_database_manager


@lru_cache
def get_run_manager() -> RunManager:
    return RunManager()


def get_app_settings() -> Settings:
    return get_settings()


_db_manager: DatabaseManager | None = None
_repository: SQLAlchemyRepository | None = None


async def get_repository() -> SQLAlchemyRepository:
    global _db_manager, _repository
    if _repository is None:
        settings = get_settings()
        _db_manager = await setup_database_manager(settings.db_path)
        _repository = SQLAlchemyRepository(_db_manager)
        await _repository.initialize()
    return _repository
