"""
LinkedIn daily scheduler.

Runs the LinkedIn agent repeatedly across the day so it can accumulate up to
the configured ``application.daily_cap`` (500) applications. The agent itself
enforces the daily cap and persists its session, so each run is OTP-free and
never exceeds the limit.

Configuration (linkedin_config.yaml -> scheduler):
    enabled:             turn the loop on/off
    interval_minutes:    pause between agent runs
    max_runs_per_day:    safety bound on how many times the agent launches
    stop_when_cap_reached: exit early once today's applied count hits the cap

Usage:
    python scripts/run_linkedin_loop.py
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "linkedin_config.yaml"


def _load_config() -> tuple[dict, int]:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    scheduler = data.get("scheduler", {})
    daily_cap = int(data.get("application", {}).get("daily_cap", 500))
    sched = {
        "enabled": bool(scheduler.get("enabled", True)),
        "interval_minutes": int(scheduler.get("interval_minutes", 180)),
        "max_runs_per_day": int(scheduler.get("max_runs_per_day", 8)),
        "stop_when_cap_reached": bool(scheduler.get("stop_when_cap_reached", True)),
    }
    return sched, daily_cap


async def _get_today_applied() -> int:
    from src.linked_agent.config.settings import get_settings
    from src.linked_agent.models.db_schema import setup_database_manager
    from src.linked_agent.database.repository import SQLAlchemyRepository

    settings = get_settings()
    db_manager = await setup_database_manager(settings.db_path)
    repo = SQLAlchemyRepository(db_manager)
    await repo.initialize()
    try:
        return await repo.get_today_application_count()
    finally:
        await repo.close()


def _run_agent_once() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "src.linked_agent.main", "run"],
        cwd=PROJECT_ROOT,
    )
    return proc.returncode


def main() -> None:
    sched, daily_cap = _load_config()

    if not sched["enabled"]:
        print("[scheduler] disabled in config — running agent once.")
        _run_agent_once()
        return

    for run_idx in range(sched["max_runs_per_day"]):
        print(
            f"\n=== LinkedIn scheduler: run {run_idx + 1}/"
            f"{sched['max_runs_per_day']} ==="
        )
        _run_agent_once()

        try:
            today = asyncio.run(_get_today_applied())
        except Exception as exc:  # pragma: no cover - diagnostics only
            print(f"[scheduler] could not read today's count: {exc}")
            today = 0

        print(f"[scheduler] applied today: {today}/{daily_cap}")

        if sched["stop_when_cap_reached"] and today >= daily_cap:
            print("[scheduler] daily cap reached — stopping.")
            break

        if run_idx < sched["max_runs_per_day"] - 1:
            seconds = sched["interval_minutes"] * 60
            print(f"[scheduler] sleeping {sched['interval_minutes']} min before next run...")
            time.sleep(seconds)

    print("[scheduler] done for today.")


if __name__ == "__main__":
    main()
