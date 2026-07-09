"""Tests for screening question API routes."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.deps import state
from api.main import app
from src.naukri_agent.models.db_schema import setup_database_manager
from src.naukri_agent.database.repository import SQLAlchemyRepository


@pytest_asyncio.fixture
async def client(tmp_path):
    db_path = tmp_path / "test.db"
    state.settings = type("S", (), {"project_root": tmp_path, "dashboard_api_key": ""})()
    state.db_manager = await setup_database_manager(db_path)
    state.repo = SQLAlchemyRepository(state.db_manager)
    await state.repo.initialize()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    session_factory = await state.db_manager.get_session_factory()
    engine = session_factory.kw["bind"]
    await engine.dispose()


class TestScreeningAPI:
    @pytest.mark.asyncio
    async def test_list_and_save_screening_question(self, client):
        await state.repo.upsert_failed_question(
            question_text="Years of React experience?",
            question_key="years of react experience",
        )

        list_res = await client.get("/api/screening-questions?status=pending")
        assert list_res.status_code == 200
        data = list_res.json()
        assert data["total"] == 1
        question_id = data["items"][0]["id"]

        save_res = await client.put(
            f"/api/screening-questions/{question_id}",
            json={"answer_text": "2 years"},
        )
        assert save_res.status_code == 200
        saved = save_res.json()
        assert saved["item"]["answer_text"] == "2 years"
        assert saved["item"]["status"] == "answered"

        stats_res = await client.get("/api/screening-questions/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["answered"] == 1
        assert stats["pending"] == 0

    @pytest.mark.asyncio
    async def test_delete_screening_question(self, client):
        await state.repo.upsert_failed_question(
            question_text="Delete via API",
            question_key="delete via api",
        )
        items = await state.repo.list_screening_questions(status="pending")
        question_id = items[0]["id"]

        delete_res = await client.delete(f"/api/screening-questions/{question_id}")
        assert delete_res.status_code == 200
        assert await state.repo.list_screening_questions(status="pending") == []
