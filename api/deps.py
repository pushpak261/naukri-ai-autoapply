"""
Shared dependencies for API route modules.
Holds global state (settings, db, repo, agent process) set during lifespan.
Uses a state object so that all imports see mutations (mutable container).
"""

from __future__ import annotations

import asyncio
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


state = AppState()
