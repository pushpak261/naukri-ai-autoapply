"""Uvicorn event-loop factory for Windows + Playwright compatibility.

Uvicorn's default asyncio loop uses SelectorEventLoop when ``--reload`` is
enabled (because ``use_subprocess=True``). On Windows, SelectorEventLoop does
not support ``asyncio.create_subprocess_exec``, which Playwright needs to start
its driver — so browser launch fails with ``NotImplementedError``.

Always use ProactorEventLoop on Windows so headed Chromium can open from the API.
"""

from __future__ import annotations

import asyncio
import sys


def create_event_loop() -> asyncio.AbstractEventLoop:
    """Zero-arg loop factory for ``uvicorn --loop backend.loop:create_event_loop``."""
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.SelectorEventLoop()
