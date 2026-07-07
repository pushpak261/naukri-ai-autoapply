import asyncio
import os
import re
import subprocess
import sys
import threading
from datetime import UTC, datetime
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import func, select

from api.deps import state
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob
from src.naukri_agent.models.db_schema import NaukriAccount

router = APIRouter(tags=["agent"])

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _agent_subprocess_env() -> dict[str, str]:
    """PYTHONPATH must include repo root and backend (models vs main live in different trees)."""
    env = os.environ.copy()
    backend_root = state.settings.project_root.resolve()
    repo_root = backend_root.parent
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root), str(backend_root)])
    return env


def _broadcast_line(line: str) -> None:
    cleaned = _strip_ansi(line)
    with state.agent_output_lock:
        state.agent_output_buffer.append(cleaned)
        if len(state.agent_output_buffer) > 2000:
            state.agent_output_buffer[:1000] = []
        for q in state.agent_sse_clients:
            try:
                q.put_nowait(cleaned)
            except asyncio.QueueFull:
                pass


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
async def start_agent():
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
                    select(NaukriAccount).where(NaukriAccount.is_active == True).limit(1)
                )
                active = result.scalar_one_or_none()
                if active:
                    state.active_account_email = active.email
        except Exception:
            pass

    cmd = [sys.executable, "-m", "src.naukri_agent.main", "run"]
    env = _agent_subprocess_env()
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
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {e}")

    state.agent_started_at = datetime.now(UTC)
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

    jobs_found = None
    jobs_applied = None
    jobs_skipped = None
    jobs_failed = None
    if running and state.agent_started_at and state.db_manager is not None:
        session_factory = await state.db_manager.get_session_factory()
        async with session_factory() as session:
            found_result = await session.execute(
                select(func.count(DBJob.id)).where(DBJob.scraped_at >= state.agent_started_at)
            )
            jobs_found = int(found_result.scalar_one() or 0)

            applied_result = await session.execute(
                select(func.count(DBApplication.id)).where(
                    DBApplication.applied_at >= state.agent_started_at,
                    DBApplication.status == ApplicationStatus.APPLIED,
                )
            )
            jobs_applied = int(applied_result.scalar_one() or 0)

            skipped_result = await session.execute(
                select(func.count(DBApplication.id)).where(
                    DBApplication.applied_at >= state.agent_started_at,
                    DBApplication.status.like("skipped%"),
                )
            )
            jobs_skipped = int(skipped_result.scalar_one() or 0)

            failed_result = await session.execute(
                select(func.count(DBApplication.id)).where(
                    DBApplication.applied_at >= state.agent_started_at,
                    DBApplication.status.in_([ApplicationStatus.FAILED, ApplicationStatus.ERROR]),
                )
            )
            jobs_failed = int(failed_result.scalar_one() or 0)

    return {
        "running": running,
        "pid": state.agent_process.pid if running else None,
        "started_at": state.agent_started_at.isoformat() if state.agent_started_at else None,
        "uptime_seconds": uptime_seconds,
        "last_run": last_run,
        "jobs_found": jobs_found,
        "jobs_applied": jobs_applied,
        "jobs_skipped": jobs_skipped,
        "jobs_failed": jobs_failed,
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
async def agent_output_stream(request: Request):
    """SSE endpoint that streams agent output in real-time."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    with state.agent_output_lock:
        state.agent_sse_clients.append(queue)
        for line in state.agent_output_buffer[-50:]:
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
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            with state.agent_output_lock:
                if queue in state.agent_sse_clients:
                    state.agent_sse_clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
