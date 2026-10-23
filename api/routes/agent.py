import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import contextvars
from datetime import UTC, datetime
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from sqlalchemy import select

from api.deps import state
from api.agent_runtime import spawn_agent, stop_agent_process, serialized_start, serialized_stop, platform_process, sse_data
from src.naukri_agent.models.db_schema import NaukriAccount
import contextlib

router = APIRouter(tags=["agent"])

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _broadcast_line(line: str) -> None:
    cleaned = _strip_ansi(line)
    with state.agent_output_lock:
        state.agent_output_buffer.append(cleaned)
        if len(state.agent_output_buffer) > 60000:
            state.agent_output_buffer[:10000] = []
        for q in state.agent_sse_clients:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(cleaned)


def _start_output_reader(process: subprocess.Popen) -> None:
    """Continuously reads stdout/stderr from agent into the shared buffer + SSE queues."""
    with state.agent_output_lock:
        state.agent_output_buffer.clear()

    loop = asyncio.get_running_loop()

    def publish(line):
        if state.agent_process is process:
            _broadcast_line(line)

    def _reader(stream) -> None:
        try:
            for raw_line in iter(stream.readline, b""):
                line = raw_line.decode("utf-8", errors="replace")
                loop.call_soon_threadsafe(publish, line)
        except (ValueError, OSError, RuntimeError):
            pass

    for stream in (process.stdout, process.stderr):
        if stream:
            t = threading.Thread(target=contextvars.copy_context().run, args=(_reader, stream), daemon=True)
            t.start()


@router.post("/api/agent/start")
@serialized_start
async def start_agent(platform: str = Query("naukri", max_length=20), job_ids: list[int] | None = None, target: Annotated[int, Query(ge=0, le=100)] = 0):
    if target not in (0, 100):
        raise HTTPException(422, "Choose normal mode (0) or Target 100")
    if platform not in ("naukri", "linkedin"):
        raise HTTPException(422, "Unknown platform")
    if target and (platform != "naukri" or job_ids):
        raise HTTPException(422, "Target 100 is available for a new Naukri discovery run only")
    if target and state.settings.application.dry_run:
        raise HTTPException(422, "Disable Dry Run before starting a submission target")
    if target and state.settings.application.daily_cap < 100:
        raise HTTPException(422, "Set the Naukri daily cap to at least 100 before starting Target 100")
    existing = platform_process(platform)
    if existing is not None:
        return {"status": "already_running", "message": "Platform agent is already running", "pid": existing.pid}
    if state.agent_process and state.agent_process.poll() is None:
        return {
            "status": "already_running",
            "message": "Agent is already running",
            "pid": state.agent_process.pid,
        }

    from api.agent_runtime import ensure_browser_capacity
    ensure_browser_capacity()
    from api.tenants import validate_agent_configuration
    await validate_agent_configuration(platform, require_search=not bool(job_ids))

    # Fallback: if in-memory state is lost (server restart), query DB for active account
    if not state.active_account_email:
        try:
            session_factory = await state.db_manager.get_session_factory()
            async with session_factory() as session:
                result = await session.execute(
                    select(NaukriAccount).where(NaukriAccount.is_active).limit(1)
                )
                active = result.scalar_one_or_none()
                if active:
                    state.active_account_email = active.email
        except Exception:
            pass

    if platform == "linkedin":
        cmd = [sys.executable, "-m", "src.linked_agent.main", "run"]
    else:
        cmd = [sys.executable, "-m", "src.naukri_agent.main", "run"]
    if target:
        cmd.extend(["--target", "100"])
    from api.tenants import agent_environment
    env = agent_environment()
    env.pop("AGENT_JOB_IDS", None)
    if job_ids:
        env["AGENT_JOB_IDS"] = json.dumps(job_ids)
    # Force unbuffered stdout/stderr so log lines reach the SSE stream in
    # real time. When stdout is a pipe (not a TTY) Python block-buffers it,
    # so a long/hung step (e.g. `playwright install` during browser launch)
    # would otherwise make the live terminal look frozen until the buffer flushes.
    env["PYTHONUNBUFFERED"] = "1"
    # Force headless mode in production (no display and not Windows)
    if not os.environ.get("DISPLAY") and sys.platform != "win32":
        env.setdefault("HEADLESS", "true")
    if state.active_account_email:
        env["NAUKRI_ACTIVE_ACCOUNT"] = state.active_account_email
    try:
        # spawn_agent puts the agent in its own process group so stop/crash can
        # kill the whole browser tree. Run it in a thread so Popen does not block
        # the event loop.
        state.agent_process = await asyncio.to_thread(
            spawn_agent,
            cmd,
            str(state.settings.project_root),
            env,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500, detail=f"Python executable not found: {sys.executable}"
        ) from None
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {e}") from e

    state.agent_queued_ids = job_ids or []
    state.agent_started_at = datetime.now(UTC)
    state.agent_platform = platform
    with state.agent_output_lock:
        state.agent_output_buffer.clear()
    _start_output_reader(state.agent_process)
    return {
        "status": "started",
        "message": "Agent started",
        "pid": state.agent_process.pid,
        "command": " ".join(cmd),
    }


@router.post("/api/agent/stop")
@serialized_stop
async def stop_agent():
    return await _stop_single_agent()


async def _stop_single_agent():
    if not state.agent_process or state.agent_process.poll() is not None:
        return {"status": "not_running", "message": "No agent process is running"}

    # Kill the whole tree so orphaned Chromium processes cannot keep the agent's
    # output pipes open and stall the event loop.
    await asyncio.to_thread(stop_agent_process, state.agent_process)
    if state.agent_process.poll() is None:
        raise HTTPException(503, "Agent is still running. Retry stop before starting another run.")
    state.agent_process = None
    state.agent_started_at = None
    # Retain the final output and platform so stopped-run logs remain inspectable.
    return {"status": "stopped", "message": "Agent process terminated"}


@router.get("/api/agent/status")
async def agent_status():
    running = state.agent_process is not None and state.agent_process.poll() is None

    try:
        last_runs = await state.repo.get_run_stats(limit=1)
    except Exception:
        last_runs = []
    last_run = last_runs[0] if last_runs else None

    uptime_seconds = None
    if running and state.agent_started_at:
        uptime_seconds = int((datetime.now(UTC) - state.agent_started_at).total_seconds())

    platform = getattr(state, "agent_platform", None)
    if running and not platform and state.agent_process:
        try:
            args = getattr(state.agent_process, "args", [])
            platform = "linkedin" if any("linked_agent" in str(arg) for arg in args) else "naukri"
        except Exception:
            platform = "naukri"

    if not running:
        platform = None

    from libs.common.run_target import target_progress_for
    root = getattr(state.settings, "project_root", None)
    target_progress = target_progress_for(root, state.agent_process if running else None) if root else None

    return {
        "running": running,
        "pid": state.agent_process.pid if running else None,
        "started_at": state.agent_started_at.isoformat() if state.agent_started_at else None,
        "uptime_seconds": uptime_seconds,
        "last_run": last_run,
        "platform": platform,
        "target_progress": target_progress,
    }


@router.get("/api/agent/output")
async def agent_output(lines: int = Query(50000, ge=1, le=60000)):

    with state.agent_output_lock:
        if not state.agent_output_buffer:
            return PlainTextResponse("Agent is stopped.\n")


        recent = state.agent_output_buffer[-lines:]
        return PlainTextResponse("".join(recent))


@router.get("/api/agent/output/stream")
async def agent_output_stream(request: Request, history: int = Query(50000, ge=0, le=60000)):
    """SSE endpoint that streams agent output in real-time."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=60000)

    with state.agent_output_lock:
        state.agent_sse_clients.append(queue)
        if history > 0:
            for line in state.agent_output_buffer[-history:]:
                try:
                    queue.put_nowait(line)
                except asyncio.QueueFull:
                    break

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=15)
                    yield sse_data(line)
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            with state.agent_output_lock:
                if queue in state.agent_sse_clients:
                    state.agent_sse_clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
