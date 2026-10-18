import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine

from src.linked_agent.database.manager import DatabaseManager
from src.linked_agent.database.repository import SQLAlchemyRepository
from src.linked_agent.models.db_schema import Base, ResumeProfile


@pytest.mark.asyncio
async def test_reparse_same_resume_updates_existing_profile():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        manager = DatabaseManager(engine)
        repo = SQLAlchemyRepository(manager)
        first = await repo.save_resume_profile('same-hash', 'resume.pdf', '{"skills":["Java"]}')
        second = await repo.save_resume_profile('same-hash', 'resume.pdf', '{"skills":["Java","SQL"]}')
        assert second.id == first.id
        assert 'SQL' in second.parsed_json
        async with manager.get_session() as session:
            assert await session.scalar(select(func.count()).select_from(ResumeProfile)) == 1
    finally:
        await engine.dispose()
