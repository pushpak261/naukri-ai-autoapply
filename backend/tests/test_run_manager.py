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

    async def fake_setup_database_manager(path):
        return object()

    def fake_create_agent(settings, db_manager):
        return FakeAgent()

    monkeypatch.setattr(
        "backend.services.run_manager.setup_database_manager",
        fake_setup_database_manager,
    )
    monkeypatch.setattr("backend.services.run_manager.create_agent", fake_create_agent)
    class FakeSettings:
        db_path = "data/test.db"
        application = type("A", (), {"daily_cap": 10, "match_score_threshold": 70})()
        run_cap_resets_daily = False

        def validate_required(self):
            return []

        def copy_for_run(self, *, cap=None, threshold=None, experience_min=None, experience_max=None):
            copied = FakeSettings()
            if cap is not None:
                copied.application = type("A", (), {"daily_cap": cap, "match_score_threshold": 70})()
                copied.run_cap_resets_daily = True
            if threshold is not None:
                th = threshold if threshold is not None else 70
                cap_val = cap if cap is not None else 10
                copied.application = type("A", (), {"daily_cap": cap_val, "match_score_threshold": th})()
            return copied

    monkeypatch.setattr(
        "backend.services.run_manager.get_settings",
        lambda: FakeSettings(),
    )

    await manager.start(RunCreate(dry_run=True))

    with pytest.raises(RuntimeError, match="already in progress"):
        await manager.start(RunCreate())

    await manager.stop()
    assert manager.get_status().status == "running"
