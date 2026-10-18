"""
Parallel multi-agent feature for the dashboard.

Lets the dashboard run several agents (e.g. Naukri + LinkedIn) at the same time.
Each platform gets its own subprocess, output buffer and SSE stream, keyed by
platform name. This is intentionally isolated from the single-agent
``/api/agent`` endpoints so the two features do not interfere.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import sys
import threading
import contextvars
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from sqlalchemy import select

from api.deps import state
from api.agent_runtime import spawn_agent, stop_agent_process, serialized_start, serialized_stop, platform_process, sse_data
from src.naukri_agent.models.db_schema import NaukriAccount

router = APIRouter(prefix="/api/multi", tags=["multi-agent"])

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

VALID_PLATFORMS = ("naukri", "linkedin")
DEFAULT_PLATFORMS = list(VALID_PLATFORMS)

_PLATFORM_CMDS = {
    "linkedin": [sys.executable, "-m", "src.linked_agent.main", "run"],
    "naukri": [sys.executable, "-m", "src.naukri_agent.main", "run"],
}


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _ensure_platform(platform: str) -> None:
    """Lazily initialise per-platform state containers."""
    if platform not in state.agent_output_buffers:
        state.agent_output_buffers[platform] = []
    if platform not in state.agent_output_locks:
        state.agent_output_locks[platform] = threading.Lock()
    if platform not in state.agent_sse_clients_map:
        state.agent_sse_clients_map[platform] = []
    if platform not in state.agent_processes:
        state.agent_processes[platform] = None
    if platform not in state.agent_started_at_map:
        state.agent_started_at_map[platform] = None


def _is_running(platform: str) -> bool:
    proc = state.agent_processes.get(platform)
    return proc is not None and proc.poll() is None


def _broadcast_line(platform: str, line: str) -> None:
    cleaned = _strip_ansi(line)
    with state.agent_output_locks[platform]:
        buffer = state.agent_output_buffers.setdefault(platform, [])
        buffer.append(cleaned)
        if len(buffer) > 60000:
            buffer[:10000] = []
        for q in list(state.agent_sse_clients_map.get(platform, [])):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(cleaned)


def _start_output_reader(platform: str, process) -> None:
    with state.agent_output_locks[platform]:
        state.agent_output_buffers.setdefault(platform, []).clear()

    loop = asyncio.get_running_loop()

    def publish(line):
        if state.agent_processes.get(platform) is process:
            _broadcast_line(platform, line)

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


@router.post("/start")
@serialized_start
async def start_agents(
    platforms: list[str] | None = Query(None, max_length=20),  # noqa: B008
):
    """Start every requested platform that is not already running.

    Defaults to all supported platforms. Returns a per-platform status map.
    """
    requested = platforms or list(DEFAULT_PLATFORMS)
    invalid = [p for p in requested if p not in VALID_PLATFORMS]
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Unknown platform(s): {', '.join(invalid)}"
        )

    # Resolve active Naukri account for env injection (best effort).
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

    results: dict[str, dict] = {}
    for platform in requested:
        _ensure_platform(platform)
        existing = platform_process(platform)
        if existing is not None:
            proc = existing
            results[platform] = {
                "status": "already_running",
                "pid": proc.pid if proc is not None else None,
            }
            continue

        from api.agent_runtime import ensure_browser_capacity
        from api.tenants import validate_agent_configuration
        try:
            await validate_agent_configuration(platform)
            ensure_browser_capacity()
        except HTTPException as error:
            results[platform] = {"status": "busy" if error.status_code == 409 else "configuration_required", "message": error.detail}
            continue
        cmd = list(_PLATFORM_CMDS[platform])
        from api.tenants import agent_environment
        env = agent_environment()
        env.pop("AGENT_JOB_IDS", None)
        # Force headless mode in production (no display and not Windows)
        if not os.environ.get("DISPLAY") and sys.platform != "win32":
            env.setdefault("HEADLESS", "true")
        if platform == "naukri" and state.active_account_email:
            env["NAUKRI_ACTIVE_ACCOUNT"] = state.active_account_email
        try:
            # spawn_agent puts each platform in its own process group so stop /
            # crash can kill the whole browser tree. Popen runs in a thread so the
            # event loop is not blocked.
            proc = await asyncio.to_thread(
                spawn_agent,
                cmd,
                str(state.settings.project_root),
                env,
            )
        except FileNotFoundError:
            results[platform] = {"status": "error", "message": "Python executable not found"}
            continue
        except OSError as e:
            results[platform] = {"status": "error", "message": f"Failed to start agent: {e}"}
            continue

        state.agent_processes[platform] = proc
        if state.agent_platform == platform:
            state.agent_platform = None
        state.agent_started_at_map[platform] = datetime.now(UTC)
        _start_output_reader(platform, proc)
        results[platform] = {"status": "started", "pid": proc.pid, "command": " ".join(cmd)}

    return {"status": "ok", "agents": results}


@router.post("/stop")
@serialized_stop
async def stop_agents(
    platform: str | None = Query(default=None, max_length=20),
):
    """Stop one platform, or all running platforms when ``platform`` is omitted."""
    if platform is not None and platform not in VALID_PLATFORMS:
        raise HTTPException(422, "Unknown platform")
    targets = [platform] if platform else list(VALID_PLATFORMS)
    results: dict[str, dict] = {}
    for plat in targets:
        _ensure_platform(plat)
        if state.agent_platform == plat and state.agent_process is not None:
            from api.routes.agent import _stop_single_agent
            result = await _stop_single_agent()
            results[plat] = {"status": result["status"]}
            continue
        proc = state.agent_processes.get(plat)
        if proc is None or proc.poll() is not None:
            results[plat] = {"status": "not_running"}
            state.agent_processes[plat] = None
            state.agent_started_at_map[plat] = None
            continue
        # Kill the whole tree: a bare terminate() leaves Chromium running, and the
        # orphan holds the agent's inherited stdout/stderr pipes open so wait()
        # would block (this runs in a thread to keep the event loop free).
        await asyncio.to_thread(stop_agent_process, proc)
        if proc.poll() is None:
            raise HTTPException(503, f"{plat} is still running. Retry stop before restarting.")
        state.agent_processes[plat] = None
        state.agent_started_at_map[plat] = None
        results[plat] = {"status": "stopped"}

    return {"status": "ok", "agents": results}


@router.get("/status")
async def agents_status():
    """Return running state and uptime per platform."""
    status_map: dict[str, dict] = {}
    for platform in VALID_PLATFORMS:
        _ensure_platform(platform)
        proc = platform_process(platform)
        running = proc is not None
        started_at = state.agent_started_at if proc is state.agent_process and running else state.agent_started_at_map.get(platform)
        uptime = None
        if running and started_at is not None:
            uptime = int((datetime.now(UTC) - started_at).total_seconds())
        status_map[platform] = {
            "running": running,
            "pid": proc.pid if running else None,
            "started_at": started_at.isoformat() if started_at is not None else None,
            "uptime_seconds": uptime,
        }

    # Surface the most recent run stats for each platform when available.
    try:
        last_runs = await state.repo.get_run_stats(limit=1)
        last_run = last_runs[0] if last_runs else None
        if last_run:
            status_map.setdefault("naukri", {})["last_run"] = last_run
    except Exception:
        pass

    return {"agents": status_map}


@router.get("/output")
async def agents_output(platform: str = Query(...), lines: int = Query(50000, ge=1, le=60000)):
    if platform not in VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    _ensure_platform(platform)
    if state.agent_platform == platform:
        from api.routes.agent import agent_output
        return await agent_output(lines)
    running = _is_running(platform)
    with state.agent_output_locks[platform]:
        buffer = state.agent_output_buffers.get(platform, [])
        if not running and not buffer:
            return PlainTextResponse(f"Agent '{platform}' is stopped. Waiting for logs...\n")
        if not buffer:
            return PlainTextResponse("Waiting for logs...\n")
        recent = buffer[-lines:]
    return PlainTextResponse("".join(recent))


@router.get("/output/stream")
async def agents_output_stream(
    request: Request,
    platform: str = Query(...),
    history: int = Query(50000, ge=0, le=60000),
):
    """SSE endpoint streaming one platform's agent output in real time."""
    if platform not in VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    _ensure_platform(platform)
    if state.agent_platform == platform:
        from api.routes.agent import agent_output_stream
        return await agent_output_stream(request, history)

    queue: asyncio.Queue = asyncio.Queue(maxsize=60000)
    with state.agent_output_locks[platform]:
        clients = state.agent_sse_clients_map.setdefault(platform, [])
        clients.append(queue)
        for line in (state.agent_output_buffers.get(platform, [])[-history:] if history else []):
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
            with state.agent_output_locks[platform]:
                clients = state.agent_sse_clients_map.get(platform, [])
                if queue in clients:
                    clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def cleanup_multi_agents() -> None:
    """Terminate all parallel agent processes (called on server shutdown)."""
    for platform, proc in list(state.agent_processes.items()):
        if proc is not None and proc.poll() is None:
            stop_agent_process(proc)
        state.agent_processes[platform] = None
        state.agent_started_at_map[platform] = None
