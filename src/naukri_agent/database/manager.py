from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.exc import SQLAlchemyError

from src.naukri_agent.utils.logger import log_error


class DatabaseManager:
    """
    Manages connections to the local SQLite database.
    """

    def __init__(
        self,
        engine: AsyncEngine,
    ) -> None:
        self.engine = engine
        self.session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """
        Returns the session factory.
        """
        return self.session_factory

    async def report_failure(self, error: Exception) -> None:
        """
        Logs a database error.
        """
        log_error(f"Database error encountered: {error}")
