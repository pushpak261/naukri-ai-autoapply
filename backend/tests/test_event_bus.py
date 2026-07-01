"""Tests for InMemoryEventBus."""

from __future__ import annotations

import asyncio

import pytest

from src.naukri_agent.core.progress import InMemoryEventBus


@pytest.mark.asyncio
async def test_event_bus_emit_and_subscribe():
    bus = InMemoryEventBus()
    queue = bus.subscribe(run_id=1)

    await bus.emit("job_updated", {"run_id": 1, "title": "Engineer"})

    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event is not None
    assert event["type"] == "job_updated"
    assert event["data"]["title"] == "Engineer"
    assert event["run_id"] == 1


@pytest.mark.asyncio
async def test_event_bus_buffer_replay():
    bus = InMemoryEventBus()
    await bus.emit("run_started", {"run_id": 2, "dry_run": True})

    queue = bus.subscribe(run_id=2)
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["type"] == "run_started"


@pytest.mark.asyncio
async def test_null_progress_reporter():
    from src.naukri_agent.core.progress import NullProgressReporter

    reporter = NullProgressReporter()
    await reporter.emit("test", {"run_id": 1})
