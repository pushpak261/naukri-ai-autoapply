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
import subprocess
import sys
import threading
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from sqlalchemy import select

from api.deps import state
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

    def _reader(stream) -> None:
        try:
            for raw_line in iter(stream.readline, b""):
                line = raw_line.decode("utf-8", errors="replace")
                _broadcast_line(platform, line)
        except (ValueError, OSError):
            pass

    for stream in (process.stdout, process.stderr):
        if stream:
            t = threading.Thread(target=_reader, args=(stream,), daemon=True)
            t.start()


@router.post("/start")
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
        if _is_running(platform):
            proc = state.agent_processes[platform]
            results[platform] = {
                "status": "already_running",
                "pid": proc.pid if proc is not None else None,
            }
            continue

        cmd = list(_PLATFORM_CMDS[platform])
        env = os.environ.copy()
        if platform == "naukri" and state.active_account_email:
            env["NAUKRI_ACTIVE_ACCOUNT"] = state.active_account_email
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(state.settings.project_root),
                env=env,
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=500, detail=f"Python executable not found: {sys.executable}"
            ) from None
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to start agent: {e}") from e

        state.agent_processes[platform] = proc
        state.agent_started_at_map[platform] = datetime.now(UTC)
        _start_output_reader(platform, proc)
        results[platform] = {"status": "started", "pid": proc.pid, "command": " ".join(cmd)}

    return {"status": "ok", "agents": results}


@router.post("/stop")
async def stop_agents(
    platform: str | None = Query(default=None, max_length=20),
):
    """Stop one platform, or all running platforms when ``platform`` is omitted."""
    targets = [platform] if platform else list(state.agent_processes.keys())
    results: dict[str, dict] = {}
    for plat in targets:
        _ensure_platform(plat)
        proc = state.agent_processes.get(plat)
        if proc is None or proc.poll() is not None:
            results[plat] = {"status": "not_running"}
            state.agent_processes[plat] = None
            state.agent_started_at_map[plat] = None
            continue
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        state.agent_processes[plat] = None
        state.agent_started_at_map[plat] = None
        with state.agent_output_locks[plat]:
            state.agent_output_buffers[plat] = []
        results[plat] = {"status": "stopped"}

    return {"status": "ok", "agents": results}


@router.get("/status")
async def agents_status():
    """Return running state and uptime per platform."""
    status_map: dict[str, dict] = {}
    for platform in VALID_PLATFORMS:
        _ensure_platform(platform)
        running = _is_running(platform)
        proc = state.agent_processes.get(platform)
        started_at = state.agent_started_at_map.get(platform)
        uptime = None
        if running and started_at is not None:
            uptime = int((datetime.now(UTC) - started_at).total_seconds())
        status_map[platform] = {
            "running": running,
            "pid": proc.pid if proc is not None else None,
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
async def agents_output(platform: str = Query(...), lines: int = 50000):
    if platform not in VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    _ensure_platform(platform)
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
    history: int = 50000,
):
    """SSE endpoint streaming one platform's agent output in real time."""
    if platform not in VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    _ensure_platform(platform)

    queue: asyncio.Queue = asyncio.Queue(maxsize=60000)
    with state.agent_output_locks[platform]:
        clients = state.agent_sse_clients_map.setdefault(platform, [])
        clients.append(queue)
        for line in state.agent_output_buffers.get(platform, [])[-history:]:
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
                    yield f"data: {line}\n\n"
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
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        state.agent_processes[platform] = None
        state.agent_started_at_map[platform] = None
