"""Target runs count confirmations, retain one run and keep existing stop guards."""

import os
import io
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from libs.common.run_target import (
    read_target_progress,
    requested_target,
    target_progress_for,
    write_target_progress,
)
from src.naukri_agent.bot import target_run
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.config.settings import ApplicationSettings
from src.naukri_agent.utils.exceptions import SearchAccessError
from tests.test_bot_agent import _process
from tests.test_bot_agent_helpers import (
    java_job,
    make_agent,
    make_applier,
    make_profile,
    make_settings,
    quiet_async,
)


def target_agent(tmp_path):
    settings = make_settings(
        tmp_path, application={"run_target": 100, "daily_cap": 100}, search={"max_pages": 5}
    )
    return make_agent(tmp_path, settings=settings)


async def test_processing_stops_at_exactly_100_receipts_not_100_attempts(tmp_path):
    agent = target_agent(tmp_path)
    applier = make_applier()
    applier.apply_to_job.side_effect = [
        {"status": ApplicationStatus.SKIPPED_SCREENING},
        {"status": ApplicationStatus.FAILED},
        *[{"status": ApplicationStatus.APPLIED} for _ in range(101)],
    ]
    with quiet_async():
        await _process(agent, [java_job(str(i)) for i in range(104)], applier=applier)
    assert agent._jobs_applied == 100
    assert applier.apply_to_job.await_count == 102
    assert agent._jobs_skipped == agent._jobs_failed == 1
    assert read_target_progress(tmp_path)["submitted"] == 100


async def test_one_log_and_login_cover_multiple_discovery_passes(tmp_path, monkeypatch):
    agent = target_agent(tmp_path)
    agent._parse_resume = AsyncMock()
    agent._resume_profile = make_profile()

    async def search_pass():
        agent._jobs_applied += 50

    agent._search_pass = AsyncMock(side_effect=search_pass)
    monkeypatch.setattr(target_run, "wait", AsyncMock())
    with quiet_async():
        await agent.run()
    agent._repo.create_run_log.assert_awaited_once()
    agent._login_handler.login.assert_awaited_once()
    assert agent._search_pass.await_count == 2
    assert agent._repo.update_run_log.await_args.kwargs["status"] == "completed"
    assert read_target_progress(tmp_path)["state"] == "target_met"
    assert agent._settings.application.skip_external_apply is True
    assert agent._settings.search.sort_by == "relevance"


async def test_daily_allowance_is_preserved_without_counting_prior_applications(
    tmp_path, monkeypatch
):
    agent = target_agent(tmp_path)
    agent._repo.get_today_application_count.side_effect = [100, 0]

    async def search_pass():
        agent._jobs_applied = 100

    pause = AsyncMock()
    monkeypatch.setattr(target_run, "wait", pause)
    await target_run.run_search_cycles(agent, AsyncMock(side_effect=search_pass))
    pause.assert_awaited_once()
    assert agent._settings.application.daily_cap == 100
    assert agent._jobs_applied == 100
    agent._repo.get_today_application_count.assert_awaited_with(source="naukri")


async def test_exhausted_discovery_never_reports_target_complete(tmp_path, monkeypatch):
    agent = target_agent(tmp_path)
    monkeypatch.setattr(target_run, "wait", AsyncMock())
    search = AsyncMock()
    await target_run.run_search_cycles(agent, search)
    assert search.await_count == 3
    assert agent._settings.search.max_pages == 15
    assert agent._jobs_applied == 0
    progress = read_target_progress(tmp_path)
    assert progress["state"] == "target_not_met"
    assert progress["reason"]


async def test_access_challenge_is_not_retried_to_reach_the_target(tmp_path):
    agent = target_agent(tmp_path)
    search = AsyncMock(side_effect=SearchAccessError("Sign in required"))
    with pytest.raises(SearchAccessError):
        await target_run.run_search_cycles(agent, search)
    search.assert_awaited_once()
    assert agent._jobs_applied == 0
    assert "verification" in agent._target_stop_reason


async def test_dry_run_cannot_masquerade_as_a_submission_target(tmp_path):
    agent = target_agent(tmp_path)
    agent._settings.application.dry_run = True
    search = AsyncMock()
    with pytest.raises(ValueError, match="Dry Run"):
        await target_run.run_search_cycles(agent, search)
    search.assert_not_awaited()


def test_unprocessed_discovered_jobs_are_available_in_the_next_pass(tmp_path):
    agent = target_agent(tmp_path)
    first, second = java_job("first"), java_job("second")
    assert target_run.fresh_jobs(agent, [first, second]) == [first, second]
    agent._target_processed.add("first")
    assert target_run.fresh_jobs(agent, [first, second]) == [second]
    assert agent._jobs_found == 2


def test_target_scope_and_checkpoint_cannot_expand_or_reuse_an_old_process(tmp_path):
    with pytest.raises(ValidationError):
        ApplicationSettings(run_target=101)
    normal = SimpleNamespace(args=["python", "-m", "src.naukri_agent.main", "run"], pid=10)
    current = SimpleNamespace(args=[*normal.args, "--target", "100"], pid=os.getpid())
    write_target_progress(tmp_path, submitted=7, state="running")
    assert requested_target(normal) == 0
    assert requested_target(current) == 100
    assert target_progress_for(tmp_path, normal) is None
    assert target_progress_for(tmp_path, current)["submitted"] == 7
    current.pid += 1
    assert target_progress_for(tmp_path, current)["submitted"] == 0
    assert read_target_progress(tmp_path / "another-tenant") is None


@pytest.mark.parametrize(
    "platform,job_ids,dry_run,cap",
    [
        ("linkedin", None, False, 100),
        ("naukri", [1], False, 100),
        ("naukri", None, True, 100),
        ("naukri", None, False, 25),
    ],
)
async def test_target_start_rejects_incompatible_modes(tmp_path, platform, job_ids, dry_run, cap):
    from fastapi import HTTPException
    from api.deps import AppState, current_state
    from api.routes.agent import start_agent
    from src.naukri_agent.config.settings import Settings

    runtime = AppState()
    runtime.settings = Settings(
        project_root=tmp_path, application={"dry_run": dry_run, "daily_cap": cap}
    )
    token = current_state.set(runtime)
    try:
        with pytest.raises(HTTPException) as error:
            await start_agent(platform=platform, job_ids=job_ids, target=100)
        assert error.value.status_code == 422
        assert runtime.agent_process is None
    finally:
        current_state.reset(token)


async def test_http_start_parses_target_and_spawns_only_the_exact_requested_mode(
    tmp_path, monkeypatch
):
    import httpx
    from fastapi import FastAPI
    from api.deps import AppState, current_state
    from api.routes import agent as routes
    from api import agent_runtime, tenants
    from src.naukri_agent.config.settings import Settings

    runtime = AppState()
    runtime.settings = Settings(project_root=tmp_path, application={"daily_cap": 100})
    proc = SimpleNamespace(pid=123, poll=lambda: None, stdout=None, stderr=None)
    commands = []

    def spawn(command, cwd, env):
        commands.append(command)
        proc.args = command
        return proc

    monkeypatch.setattr(routes, "spawn_agent", spawn)
    monkeypatch.setattr(agent_runtime, "ensure_browser_capacity", lambda: None)
    monkeypatch.setattr(tenants, "validate_agent_configuration", AsyncMock())
    app = FastAPI()
    app.include_router(routes.router)
    token = current_state.set(runtime)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            rejected = await client.post("/api/agent/start?platform=naukri&target=25")
            assert rejected.status_code == 422
            assert not commands
            response = await client.post("/api/agent/start?platform=naukri&target=100")
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "started"
            assert commands[0][-2:] == ["--target", "100"]
            assert len(commands) == 1
    finally:
        current_state.reset(token)


def test_terminal_flush_after_log_close_does_not_turn_success_into_an_exit_error():
    from src.naukri_agent.utils.terminal_logging import DualStream

    original, log = io.StringIO(), io.StringIO()
    stream = DualStream(original, log, threading.Lock())
    log.close()
    stream.write("Completed\n")
    stream.flush()
    assert original.getvalue() == "Completed\n"
