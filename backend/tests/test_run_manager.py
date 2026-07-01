"""Tests for RunManager."""

from __future__ import annotations

import pytest

from backend.schemas.run import RunCreate
from backend.services.run_manager import RunManager


@pytest.mark.asyncio
async def test_run_manager_initial_status():
    manager = RunManager()
    status = manager.get_status()
    assert status.status == "idle"
    assert status.run_id is None


@pytest.mark.asyncio
async def test_run_manager_rejects_concurrent_start(monkeypatch):
    manager = RunManager()

    class FakeAgent:
        _run_log_id = 99
        _jobs_found = 0
        _jobs_applied = 0
        _jobs_skipped = 0
        _jobs_failed = 0
        _interrupted = False
        _phase = "running"
        _settings = type("S", (), {"application": type("A", (), {"daily_cap": 10})()})()
        _daily_applied = 0

        async def run(self, dry_run: bool = False) -> None:
            import asyncio

            await asyncio.sleep(60)

    async def fake_init_db(path):
        return lambda: None

    def fake_create_agent(settings, session_factory, progress_reporter=None):
        return FakeAgent()

    monkeypatch.setattr("backend.services.run_manager.init_db", fake_init_db)
    monkeypatch.setattr("backend.services.run_manager.create_agent", fake_create_agent)
    monkeypatch.setattr(
        "backend.services.run_manager.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "db_path": "data/test.db",
                "application": type("A", (), {"daily_cap": 10, "match_score_threshold": 70})(),
                "validate_required": lambda self: [],
            },
        )(),
    )

    await manager.start(RunCreate(dry_run=True))

    with pytest.raises(RuntimeError, match="already in progress"):
        await manager.start(RunCreate())

    await manager.stop()
    assert manager.get_status().status == "running"
