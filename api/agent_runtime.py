"""
Shared agent-run lifecycle helpers.

Centralises the cross-cutting concerns of running agent subprocesses so the
single-agent and multi-agent routes behave consistently and the platform never
ends up with two agents for the same site (which would double-apply jobs and
fight over the browser):

  * ``acquire_platform`` / ``release_platform`` — a single concurrency gate.
  * ``spawn_agent`` / ``stop_agent_process`` — cross-platform spawning that
    puts each agent in its own process group so the *entire* tree (including
    the Chromium/Playwright children) can be killed on stop or crash, instead
    of leaking orphaned browser processes.
  * ``recover_stuck_runs`` — called by a supervisor to flip any ``RunLog`` that
    is stuck in ``running`` (e.g. after a hard kill) to ``error``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
from datetime import UTC, datetime
from typing import Any

from api.deps import state
from libs.common.metrics import (
    AGENT_BLOCKED,
    AGENT_LAST_RUN_TIMESTAMP,
    AGENT_RUNNING,
)


def _is_windows() -> bool:
    return os.name == "nt"


def _ensure_lock() -> asyncio.Lock:
    if state.agent_run_lock is None:
        state.agent_run_lock = asyncio.Lock()
    return state.agent_run_lock


def _touch_run_metric() -> None:
    if AGENT_LAST_RUN_TIMESTAMP is not None:
        AGENT_LAST_RUN_TIMESTAMP.set(__import__("time").time())


async def acquire_platform(platform: str) -> bool:
    """Try to mark a platform as running. Returns True if acquired."""
    async with _ensure_lock():
        if platform in state.agent_active_platforms:
            return False
        state.agent_active_platforms.add(platform)
        if AGENT_RUNNING is not None:
            AGENT_RUNNING.inc()
        _touch_run_metric()
        return True


async def release_platform(platform: str) -> None:
    async with _ensure_lock():
        state.agent_active_platforms.discard(platform)
        if AGENT_RUNNING is not None and state.agent_active_platforms:
            # Keep the gauge at the number of still-active platforms.
            AGENT_RUNNING.set(len(state.agent_active_platforms))
        elif AGENT_RUNNING is not None:
            AGENT_RUNNING.set(0)
        _touch_run_metric()


def _spawn_kwargs() -> dict:
    """Process-group flags so we can kill the whole tree on stop/crash."""
    if _is_windows():
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def spawn_agent(cmd: list[str], cwd: str, env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        **_spawn_kwargs(),
    )


def stop_agent_process(proc: subprocess.Popen | None, graceful_timeout: float = 10.0) -> None:
    """Terminate a process tree gracefully (SIGINT on POSIX) then forcibly."""
    if proc is None or proc.poll() is not None:
        return
    if _is_windows():
        # taskkill /T/F removes the whole tree (python + browser children).
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        return

    # POSIX: SIGINT lets the agent run its graceful shutdown (_cleanup).
    with contextlib.suppress(Exception):
        os.killpg(os.getpgid(proc.pid), signal.SIGINT)
    try:
        proc.wait(timeout=graceful_timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(Exception):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        with contextlib.suppress(Exception):
            proc.kill()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)


async def recover_stuck_runs(repo: Any) -> None:
    """Mark any RunLog left in ``running`` as ``error`` (e.g. after a crash)."""
    with contextlib.suppress(Exception):
        await repo.fail_stuck_runs("Run ended unexpectedly (process terminated).")


async def mark_agent_blocked(settings: Any, reason: str, job: Any | None = None) -> None:
    """Pause the agent due to an external block and notify an operator.

    Sets the ``agent_blocked`` metric and (best-effort) sends a notification so
    a human can solve the CAPTCHA/OTP or rotate the IP before resuming.
    """
    state.agent_blocked_reason = reason
    if AGENT_BLOCKED is not None:
        AGENT_BLOCKED.set(1)
    try:
        from src.naukri_agent.utils.notification import send_notification

        target = f" ({job.title} @ {job.company})" if job else ""
        await send_notification(
            settings,
            "agent.blocked",
            f"Agent paused: Naukri {reason} detected{target}",
            f"<p>The agent stopped applying because a <b>{reason}</b> was detected "
            f"on Naukri. Resolve it (solve the challenge / rotate the IP) and "
            f"restart the run.</p>",
        )
    except Exception:
        # Notification must never break the agent loop.
        pass


def clear_agent_blocked() -> None:
    """Clear the blocked state (e.g. when a new run starts)."""
    state.agent_blocked_reason = None
    if AGENT_BLOCKED is not None:
        AGENT_BLOCKED.set(0)


async def supervise(
    repo: Any,
    *,
    max_runtime_seconds: float = 3600.0,
    interval_seconds: float = 15.0,
) -> None:
    """Background supervisor: kills overrun agents and recovers stuck run logs.

    Runs until cancelled. Checks the single-agent process and every multi-agent
    platform process; if a tracked process has died, releases the platform and
    flips the stuck ``RunLog`` to ``error``. If a process exceeds the max
    runtime, it is terminated (also marked error).
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            now = datetime.now(UTC)

            async with _ensure_lock():
                single = state.agent_process
                single_platform = getattr(state, "agent_platform", None)
                single_started = getattr(state, "agent_started_at", None)
                platforms = list(state.agent_processes.items())

            async def _check(proc: subprocess.Popen | None, platform: str | None, started_at: datetime | None, now_ts: datetime):
                if proc is None or not platform:
                    return
                dead = proc.poll() is not None
                overrun = (
                    started_at is not None
                    and (now_ts - started_at).total_seconds() > max_runtime_seconds
                )
                if dead or overrun:
                    if overrun and not dead:
                        stop_agent_process(proc)
                    await release_platform(platform)
                    await recover_stuck_runs(repo)
                    if getattr(state, "agent_platform", None) == platform and state.agent_process is proc:
                        state.agent_process = None
                        state.agent_started_at = None
                        state.agent_platform = None
                    if state.agent_processes.get(platform) is proc:
                        state.agent_processes[platform] = None
                        state.agent_started_at_map[platform] = None

            if single_platform:
                await _check(single, single_platform, single_started, now)
            for platform, proc in platforms:
                if proc is None:
                    continue
                started = state.agent_started_at_map.get(platform)
                await _check(proc, platform, started, now)
        except Exception:
            # Supervisor must never crash the service.
            pass
