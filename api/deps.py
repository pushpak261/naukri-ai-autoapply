"""
Shared dependencies for API route modules.
Holds global state (settings, db, repo, agent process) set during lifespan.
Uses a state object so that all imports see mutations (mutable container).
"""

from __future__ import annotations

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

    autopilot_config: dict = None

    active_account_email: str | None = None


state = AppState()
