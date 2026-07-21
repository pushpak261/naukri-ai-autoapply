import asyncio
import os
import re
import subprocess
import sys
import threading
from datetime import UTC, datetime
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from sqlalchemy import select

from api.deps import state
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
        if len(state.agent_output_buffer) > 2000:
            state.agent_output_buffer[:1000] = []
        for q in state.agent_sse_clients:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(cleaned)


def _start_output_reader(process: subprocess.Popen) -> None:
    """Continuously reads stdout/stderr from agent into the shared buffer + SSE queues."""
    with state.agent_output_lock:
        state.agent_output_buffer.clear()

    def _reader(stream) -> None:
        try:
            for raw_line in iter(stream.readline, b""):
                line = raw_line.decode("utf-8", errors="replace")
                _broadcast_line(line)
        except (ValueError, OSError):
            pass

    for stream in (process.stdout, process.stderr):
        if stream:
            t = threading.Thread(target=_reader, args=(stream,), daemon=True)
            t.start()


@router.post("/api/agent/start")
async def start_agent(platform: str = Query("naukri", max_length=20)):
    if state.agent_process and state.agent_process.poll() is None:
        return {
            "status": "already_running",
            "message": "Agent is already running",
            "pid": state.agent_process.pid,
        }

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
    env = os.environ.copy()
    if state.active_account_email:
        env["NAUKRI_ACTIVE_ACCOUNT"] = state.active_account_email
    try:
        state.agent_process = subprocess.Popen(
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
async def stop_agent():
    if not state.agent_process or state.agent_process.poll() is not None:
        return {"status": "not_running", "message": "No agent process is running"}

    state.agent_process.terminate()
    try:
        state.agent_process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        state.agent_process.kill()
        state.agent_process.wait()
    state.agent_process = None
    state.agent_started_at = None
    state.agent_platform = None
    with state.agent_output_lock:
        state.agent_output_buffer.clear()
    return {"status": "stopped", "message": "Agent process terminated"}


@router.get("/api/agent/status")
async def agent_status():
    running = state.agent_process is not None and state.agent_process.poll() is None

    last_runs = await state.repo.get_run_stats(limit=1)
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

    return {
        "running": running,
        "pid": state.agent_process.pid if running else None,
        "started_at": state.agent_started_at.isoformat() if state.agent_started_at else None,
        "uptime_seconds": uptime_seconds,
        "last_run": last_run,
        "platform": platform,
    }


@router.get("/api/agent/output")
async def agent_output(lines: int = 50):
    running = state.agent_process is not None and state.agent_process.poll() is None

    with state.agent_output_lock:
        if not running and not state.agent_output_buffer:
            return PlainTextResponse("Agent process not found", status_code=404)

        if not state.agent_output_buffer:
            return PlainTextResponse("Waiting for logs...\n")

        recent = state.agent_output_buffer[-lines:]
        return PlainTextResponse("".join(recent))


@router.get("/api/agent/output/stream")
async def agent_output_stream(request: Request, history: int = 50):
    """SSE endpoint that streams agent output in real-time."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)

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
                    yield f"data: {line}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            with state.agent_output_lock:
                if queue in state.agent_sse_clients:
                    state.agent_sse_clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
