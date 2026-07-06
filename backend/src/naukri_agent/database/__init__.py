# src/database/__init__.py
"""Database layer for the Naukri Agent."""

from src.naukri_agent.models.db_schema import setup_database_manager
from src.naukri_agent.database.repository import SQLAlchemyRepository

__all__ = ["setup_database_manager", "SQLAlchemyRepository"]
