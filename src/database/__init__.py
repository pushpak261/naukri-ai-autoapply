# src/database/__init__.py
"""Database layer for the Naukri Agent."""

from src.database.models import init_db
from src.database.repository import SQLAlchemyRepository

__all__ = ["init_db", "SQLAlchemyRepository"]
