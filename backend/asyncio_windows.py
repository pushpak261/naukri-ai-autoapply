"""Windows asyncio helpers for Playwright + uvicorn compatibility."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from src.naukri_agent.core.interfaces import IProgressReporter

T = TypeVar("T")


def needs_proactor_thread() -> bool:
    """True when Playwright cannot spawn subprocesses on the active loop (Windows + SelectorEventLoop)."""
    if sys.platform != "win32":
        return False
    return not isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop)


class LoopBridgingProgressReporter:
    """Forward progress events from a worker thread loop to the API server's loop."""

    def __init__(self, inner: IProgressReporter, main_loop: asyncio.AbstractEventLoop) -> None:
        self._inner = inner
        self._main_loop = main_loop

    async def emit(self, event_type: str, payload: dict) -> None:
        if asyncio.get_running_loop() is self._main_loop:
            await self._inner.emit(event_type, payload)
            return
        future = asyncio.run_coroutine_threadsafe(
            self._inner.emit(event_type, payload),
            self._main_loop,
        )
        await asyncio.wrap_future(future)


async def run_on_playwright_loop(
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
) -> T:
    """Run a coroutine on ProactorEventLoop when the active loop cannot spawn subprocesses."""
    if not needs_proactor_thread():
        return await coro_factory()

    main_loop = asyncio.get_running_loop()

    def _thread_main() -> T:
        proactor = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(proactor)
        try:
            return proactor.run_until_complete(coro_factory())
        finally:
            proactor.close()

    return await main_loop.run_in_executor(None, _thread_main)
