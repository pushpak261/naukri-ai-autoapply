"""Tests for screening question repository operations."""

import json

import pytest
import pytest_asyncio

from src.naukri_agent.models.db_schema import setup_database_manager
from src.naukri_agent.database.repository import SQLAlchemyRepository


@pytest_asyncio.fixture
async def repo(tmp_path):
    db_path = tmp_path / "test.db"
    db_manager = await setup_database_manager(db_path)
    repository = SQLAlchemyRepository(db_manager)
    await repository.initialize()
    yield repository

    session_factory = await db_manager.get_session_factory()
    engine = session_factory.kw["bind"]
    await engine.dispose()


class TestScreeningQuestions:
    @pytest.mark.asyncio
    async def test_upsert_failed_question_creates_pending(self, repo):
        await repo.upsert_failed_question(
            question_text="How many years of Spring Boot experience?",
            question_key="how many years of spring boot experience",
            question_type="text",
            options=[],
        )

        items = await repo.list_screening_questions(status="pending")
        assert len(items) == 1
        assert items[0]["question_text"] == "How many years of Spring Boot experience?"
        assert items[0]["status"] == "pending"
        assert items[0]["failure_count"] == 1

    @pytest.mark.asyncio
    async def test_upsert_increments_failure_count(self, repo):
        await repo.upsert_failed_question(
            question_text="Describe your biggest project",
            question_key="describe your biggest project",
        )
        await repo.upsert_failed_question(
            question_text="Describe your biggest project",
            question_key="describe your biggest project",
        )

        items = await repo.list_screening_questions(status="pending")
        assert items[0]["failure_count"] == 2

    @pytest.mark.asyncio
    async def test_save_user_answer_marks_answered(self, repo):
        await repo.upsert_failed_question(
            question_text="Are you willing to relocate?",
            question_key="are you willing to relocate",
            question_type="radio",
            options=[{"text": "Yes"}, {"text": "No"}],
        )
        items = await repo.list_screening_questions(status="pending")
        saved = await repo.save_user_screening_answer(items[0]["id"], "Yes")

        assert saved is not None
        assert saved["answer_text"] == "Yes"
        assert saved["status"] == "answered"
        assert saved["source"] == "user"

        answer = await repo.get_screening_answer("are you willing to relocate")
        assert answer == "Yes"

    @pytest.mark.asyncio
    async def test_upsert_skips_answered_user_question(self, repo):
        await repo.upsert_failed_question(
            question_text="Notice period?",
            question_key="notice period",
        )
        items = await repo.list_screening_questions(status="pending")
        await repo.save_user_screening_answer(items[0]["id"], "Immediate")

        await repo.upsert_failed_question(
            question_text="Notice period?",
            question_key="notice period",
        )

        answer = await repo.get_screening_answer("notice period")
        assert answer == "Immediate"
        pending = await repo.list_screening_questions(status="pending")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_migrate_qa_cache_to_db(self, repo, tmp_path):
        cache_path = tmp_path / "qa_cache.json"
        cache_path.write_text(
            json.dumps(
                {
                    "what is your current ctc": "10 LPA",
                    "notice period": "Immediate",
                }
            ),
            encoding="utf-8",
        )

        imported = await repo.migrate_qa_cache_to_db(cache_path)
        assert imported == 2

        imported_again = await repo.migrate_qa_cache_to_db(cache_path)
        assert imported_again == 0

        answered = await repo.list_screening_questions(status="answered")
        assert len(answered) == 2

    @pytest.mark.asyncio
    async def test_delete_screening_question(self, repo):
        await repo.upsert_failed_question(
            question_text="Delete me",
            question_key="delete me",
        )
        items = await repo.list_screening_questions(status="pending")
        deleted = await repo.delete_screening_question(items[0]["id"])
        assert deleted is True
        assert await repo.list_screening_questions(status="pending") == []

    @pytest.mark.asyncio
    async def test_stats(self, repo):
        await repo.upsert_failed_question("Q1", "q1")
        await repo.upsert_failed_question("Q2", "q2")
        items = await repo.list_screening_questions(status="pending")
        await repo.save_user_screening_answer(items[0]["id"], "A1")

        stats = await repo.get_screening_question_stats()
        assert stats["pending"] == 1
        assert stats["answered"] == 1
        assert stats["total"] == 2
