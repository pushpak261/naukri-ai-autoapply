"""Serialize access to the main search browser page (search producer only)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


class BrowserGate:
    """Async lock ensuring only one coroutine uses the main search page at a time."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        async with self._lock:
            yield


# Alias for search-only semantics
SearchBrowserGate = BrowserGate
