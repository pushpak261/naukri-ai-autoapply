"""Serialize access to the shared browser page across search and apply tasks."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


class BrowserGate:
    """Async lock ensuring only one coroutine uses the browser page at a time."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        async with self._lock:
            yield
