# src/database/__init__.py
"""Database layer for the Naukri Agent."""

from src.naukri_agent.database.models import init_db
from src.naukri_agent.database.repository import SQLAlchemyRepository

__all__ = ["init_db", "SQLAlchemyRepository"]
