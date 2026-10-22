from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from api.deps import AppState, current_state
from api.routes.screening import ScreeningAnswers, save_screening_answers, screening_questions
from libs.common.screening_review import ScreeningReviewStore
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.db_schema import Application, Job, setup_database_manager


@pytest.mark.asyncio
async def test_saving_answers_queues_only_resolved_jobs_and_never_retries_uncertain(tmp_path):
    runtime = AppState()
    runtime.settings = Settings(project_root=tmp_path)
    runtime.db_manager = await setup_database_manager(tmp_path / "jobs.db")
    token = current_state.set(runtime)
    try:
        async with runtime.db_manager.session_factory() as session, session.begin():
            session.add_all(
                [
                    Job(
                        id=i,
                        naukri_job_id=str(i),
                        title="Java",
                        company="Example",
                        url="https://www.naukri.com/jobs",
                        source="naukri",
                    )
                    for i in [1, 2]
                ]
            )
        async with runtime.db_manager.session_factory() as session, session.begin():
            session.add_all(
                [
                    Application(job_id=1, status="skipped_screening"),
                    Application(job_id=2, status="uncertain"),
                ]
            )
        store = ScreeningReviewStore(tmp_path)
        q = {"question": "Do you need sponsorship?", "type": "text", "options": ["Yes", "No"]}
        identifier = store.remember(q, SimpleNamespace(id=1, title="Java"))
        store.remember(q, SimpleNamespace(id=2, title="Java"))
        assert len((await screening_questions())["items"]) == 1
        result = await save_screening_answers(
            ScreeningAnswers(answers={identifier: "No"}, queue_jobs=True)
        )
        assert result["saved"] == 1 and result["queued"] == 1
        async with runtime.db_manager.session_factory() as session:
            states = dict(
                (await session.execute(select(Application.job_id, Application.status))).all()
            )
        assert states == {1: "pending_retry", 2: "uncertain"}
        with pytest.raises(HTTPException) as error:
            await save_screening_answers(ScreeningAnswers(answers={identifier: "Maybe"}))
        assert error.value.status_code == 422
    finally:
        current_state.reset(token)
        await runtime.db_manager.engine.dispose()


@pytest.mark.asyncio
async def test_review_api_cannot_read_or_write_another_tenants_question(tmp_path):
    store = ScreeningReviewStore(tmp_path / "first")
    identifier = store.remember(
        {"question": "Private question"}, SimpleNamespace(id=1, title="Java")
    )
    runtime = AppState()
    runtime.settings = Settings(project_root=tmp_path / "second")
    token = current_state.set(runtime)
    try:
        assert (await screening_questions())["items"] == []
        with pytest.raises(HTTPException) as error:
            await save_screening_answers(ScreeningAnswers(answers={identifier: "Private answer"}))
        assert error.value.status_code == 422
        assert store.pending()[0]["id"] == identifier
    finally:
        current_state.reset(token)


def test_empty_answer_batches_and_values_are_rejected():
    with pytest.raises(ValidationError):
        ScreeningAnswers(answers={})
    with pytest.raises(ValidationError):
        ScreeningAnswers(answers={"id": ""})


def test_last_working_date_must_be_explicit_and_valid():
    from api.routes.config import ConfigUpdate
    from src.naukri_agent.config.settings import ProfileSettings

    for model in (ProfileSettings, ConfigUpdate):
        assert model(last_working_date="2026-12-01").last_working_date == "2026-12-01"
        assert model(last_working_date="").last_working_date == ""
        with pytest.raises(ValidationError):
            model(last_working_date="not fixed")
