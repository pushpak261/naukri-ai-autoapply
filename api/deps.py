"""
Shared dependencies for API route modules.
Holds global state (settings, db, repo, agent process) set during lifespan.
Uses a state object so that all imports see mutations (mutable container).
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import threading
from datetime import datetime
from subprocess import Popen
from typing import Any


class AppState:
    settings: Any = None
    db_manager: Any = None
    repo: Any = None

    agent_process: Popen | None = None
    agent_started_at: datetime | None = None
    agent_output_buffer: list[str] = []
    agent_output_lock: threading.Lock = threading.Lock()
    agent_sse_clients: list[Any] = []

    autopilot_config: dict | None = None

    active_account_email: str | None = None

    # ---------------------------------------------------------------------------
    # Parallel multi-agent feature state
    # Each platform (e.g. "naukri", "linkedin") runs in its own subprocess with
    # its own output buffer and SSE client list, so several agents can run
    # concurrently from the dashboard.
    # ---------------------------------------------------------------------------
    agent_processes: dict[str, Popen | None] = {}
    agent_started_at_map: dict[str, datetime | None] = {}
    agent_output_buffers: dict[str, list[str]] = {}
    agent_output_locks: dict[str, threading.Lock] = {}
    agent_sse_clients_map: dict[str, list[Any]] = {}

    # Agent runtime state
    agent_run_lock: asyncio.Lock | None = None
    agent_active_platforms: set[str] = set()
    agent_blocked_reason: str | None = None
    agent_platform: str | None = None


# Mutable values must belong to an instance, never to a shared class container.
    def __init__(self):
        self.agent_output_buffer = []
        self.agent_output_lock = threading.Lock()
        self.agent_sse_clients = []
        self.agent_processes = {}
        self.agent_started_at_map = {}
        self.agent_output_buffers = {}
        self.agent_output_locks = {}
        self.agent_sse_clients_map = {}
        self.agent_active_platforms = set()
        self.agent_queued_ids = []
        self.application_sync_task = None
        self.application_sync_result = {"running": False}
        self.background_tasks = []
        self.user_id = None



root_state = AppState()
current_state: ContextVar[AppState | None] = ContextVar("dashboard_state", default=None)


def current_runtime():
    return current_state.get() or root_state


class StateProxy:
    def __getattr__(self, name):
        return getattr(current_runtime(), name)

    def __setattr__(self, name, value):
        setattr(current_runtime(), name, value)

    def __delattr__(self, name):
        delattr(current_runtime(), name)


state = StateProxy()
