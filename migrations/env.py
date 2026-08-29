"""Alembic environment for the Naukri platform (async)."""

from __future__ import annotations

import asyncio
import os

import sqlalchemy.pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Make the project importable when alembic is run from the repo root.
from src.naukri_agent.models.db_schema import Base  # noqa: E402

config = context.config

target_metadata = Base.metadata


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./data/naukri_agent.db"
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def _run_async_migrations() -> None:
    url = _get_url()
    connectable = create_async_engine(url, poolclass=sqlalchemy.pool.NullPool)

    async def _run() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(lambda conn: context.run_migrations())
        await connectable.dispose()

    asyncio.run(_run())


def run_migrations_online() -> None:
    _run_async_migrations()


run_migrations_online()
