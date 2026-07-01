"""
Progress reporting for the Naukri Agent.

Provides a no-op reporter for CLI usage and an in-memory event bus
for the web dashboard SSE stream.
"""

from __future__ import annotations

import asyncio
import itertools
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.core.interfaces import IProgressReporter

_event_counter = itertools.count(1)


def _new_event_id() -> str:
    return f"evt_{next(_event_counter)}"


def job_event_payload(job: Job, status: str, **extra: Any) -> dict[str, Any]:
    """Serialize a Job entity into an SSE job_updated data payload."""
    payload: dict[str, Any] = {
        "naukri_job_id": job.naukri_job_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "experience": job.experience,
        "salary": job.salary,
        "status": status,
        "url": job.url,
        "posted_date": job.posted_date,
        "skills": job.skills,
        "is_verified": job.is_verified,
        "company_rating": job.company_rating,
        "is_external_apply": job.is_external_apply,
        "external_apply_url": job.external_apply_url,
        "hiring_for": job.hiring_for,
        "is_consultant_post": job.is_consultant_post,
        "match_score": None,
        "heuristic_score": None,
        "match_reasoning": None,
        "reason": None,
    }
    payload.update(extra)
    return payload


class NullProgressReporter:
    """No-op reporter used by the CLI — zero overhead."""

    async def emit(self, event_type: str, payload: dict) -> None:
        pass


class InMemoryEventBus:
    """
    Buffers events per run_id and fans out to SSE subscriber queues.

    Each subscriber receives a dedicated asyncio.Queue. Events are also
    retained in a per-run buffer for late-connecting clients.
    """

    def __init__(self, buffer_limit: int = 5000) -> None:
        self._buffer_limit = buffer_limit
        self._buffers: dict[int, list[dict]] = defaultdict(list)
        self._subscribers: dict[int, list[asyncio.Queue[dict | None]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def emit(self, event_type: str, payload: dict) -> None:
        run_id = payload.get("run_id")
        if run_id is None:
            return

        event = {
            "id": _new_event_id(),
            "run_id": run_id,
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {k: v for k, v in payload.items() if k != "run_id"},
        }

        async with self._lock:
            buf = self._buffers[run_id]
            buf.append(event)
            if len(buf) > self._buffer_limit:
                del buf[: len(buf) - self._buffer_limit]
            queues = list(self._subscribers.get(run_id, []))

        for queue in queues:
            await queue.put(event)

    def subscribe(self, run_id: int) -> asyncio.Queue[dict | None]:
        """Create a new subscriber queue pre-filled with buffered events."""
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        for event in self._buffers.get(run_id, []):
            queue.put_nowait(event)
        self._subscribers[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: int, queue: asyncio.Queue[dict | None]) -> None:
        subs = self._subscribers.get(run_id, [])
        if queue in subs:
            subs.remove(queue)

    async def close_subscribers(self, run_id: int) -> None:
        """Signal all subscribers for a run that the stream is done."""
        async with self._lock:
            queues = list(self._subscribers.get(run_id, []))
        for queue in queues:
            await queue.put(None)

    def clear_run(self, run_id: int) -> None:
        self._buffers.pop(run_id, None)
        self._subscribers.pop(run_id, None)


def counters_payload(
    run_id: int,
    *,
    jobs_found: int = 0,
    jobs_applied: int = 0,
    jobs_skipped: int = 0,
    jobs_failed: int = 0,
    daily_cap_remaining: int = 0,
    processed_count: int = 0,
    total_queued: int = 0,
    phase: str = "",
) -> dict:
    return {
        "run_id": run_id,
        "jobs_found": jobs_found,
        "jobs_applied": jobs_applied,
        "jobs_skipped": jobs_skipped,
        "jobs_failed": jobs_failed,
        "daily_cap_remaining": daily_cap_remaining,
        "processed_count": processed_count,
        "total_queued": total_queued,
        "phase": phase,
    }
