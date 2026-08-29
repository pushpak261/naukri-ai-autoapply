"""Agent Orchestrator Service — starts/stops/streams the Naukri/LinkedIn agents.

Owns the agent subprocess lifecycle, SSE streaming, autopilot config, webhooks
and browser-session management. Cleans up any running agent processes on
shutdown and runs a supervisor that recovers crashed/stuck run logs.
"""

from __future__ import annotations

import asyncio
import os

from api.agent_runtime import supervise, stop_agent_process
from api.deps import state
from api.routes import agent as agent_router
from api.routes import autopilot as autopilot_router
from api.routes import multi_agent as multi_agent_router
from api.routes import sessions as sessions_router
from api.routes import webhooks as webhooks_router
from libs.common import make_service_app

_supervisor_task: asyncio.Task | None = None


async def _startup_agent(_app) -> None:
    global _supervisor_task
    max_runtime = float(os.environ.get("AGENT_MAX_RUNTIME_SECONDS", "3600"))
    _supervisor_task = asyncio.create_task(
        supervise(state.repo, max_runtime_seconds=max_runtime)
    )


async def _shutdown_agent(_app) -> None:
    global _supervisor_task
    if _supervisor_task is not None:
        _supervisor_task.cancel()
        _supervisor_task = None
    procs = []
    if state.agent_process and state.agent_process.poll() is None:
        procs.append(state.agent_process)
    for proc in state.agent_processes.values():
        if proc and proc.poll() is None:
            procs.append(proc)
    for proc in procs:
        stop_agent_process(proc)
    state.agent_process = None
    state.agent_processes = {}


app = make_service_app(
    name="agent-service",
    routers=[agent_router, multi_agent_router, autopilot_router, webhooks_router, sessions_router],
    resolve_active_account=True,
    on_startup=_startup_agent,
    on_shutdown=_shutdown_agent,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8107)
