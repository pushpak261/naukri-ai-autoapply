"""Manages a single active agent run for the web API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.schemas.run import RunCreate, RunStatus
from src.naukri_agent.config.settings import Settings, get_settings
from src.naukri_agent.core.progress import InMemoryEventBus
from src.naukri_agent.database.models import init_db
from src.naukri_agent.main import create_agent
from src.naukri_agent.orchestrator.agent import NaukriAgent


@dataclass
class _RunState:
    task: asyncio.Task | None = None
    agent: NaukriAgent | None = None
    run_id: int | None = None
    dry_run: bool = False
    error: str | None = None
    phase: str = ""
    counters: dict = field(default_factory=dict)


class RunManager:
    """Enforces one active agent run at a time."""

    def __init__(self) -> None:
        self._event_bus = InMemoryEventBus()
        self._state = _RunState()
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._lock = asyncio.Lock()

    @property
    def event_bus(self) -> InMemoryEventBus:
        return self._event_bus

    async def _ensure_db(self, settings: Settings) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = await init_db(settings.db_path)
        return self._session_factory

    def get_status(self) -> RunStatus:
        state = self._state
        agent = state.agent
        if state.task and not state.task.done():
            status = "running"
            phase = getattr(agent, "_phase", state.phase) if agent else state.phase
            jobs_found = getattr(agent, "_jobs_found", 0) if agent else 0
            jobs_applied = getattr(agent, "_jobs_applied", 0) if agent else 0
            jobs_skipped = getattr(agent, "_jobs_skipped", 0) if agent else 0
            jobs_failed = getattr(agent, "_jobs_failed", 0) if agent else 0
            daily_cap = 0
            daily_applied = 0
            if agent:
                daily_cap = agent._settings.application.daily_cap
                daily_applied = getattr(agent, "_daily_applied", 0)
            return RunStatus(
                run_id=state.run_id,
                status=status,
                phase=phase,
                dry_run=state.dry_run,
                jobs_found=jobs_found,
                jobs_applied=jobs_applied,
                jobs_skipped=jobs_skipped,
                jobs_failed=jobs_failed,
                daily_cap_remaining=max(0, daily_cap - daily_applied),
                processed_count=jobs_applied + jobs_skipped + jobs_failed,
                total_queued=jobs_found,
            )
        if state.task and state.task.done() and state.error:
            return RunStatus(
                run_id=state.run_id,
                status="error",
                phase="error",
                dry_run=state.dry_run,
                error=state.error,
                **state.counters,
            )
        if state.run_id and state.task and state.task.done():
            agent_phase = getattr(agent, "_phase", "completed") if agent else "completed"
            agent_errored = getattr(agent, "_run_errored", False) if agent else False
            if agent_errored or agent_phase == "error":
                return RunStatus(
                    run_id=state.run_id,
                    status="error",
                    phase="error",
                    dry_run=state.dry_run,
                    error=state.error,
                    **state.counters,
                )
            return RunStatus(
                run_id=state.run_id,
                status="completed",
                phase="completed",
                dry_run=state.dry_run,
                **state.counters,
            )
        return RunStatus()

    async def start(self, options: RunCreate) -> RunStatus:
        async with self._lock:
            if self._state.task and not self._state.task.done():
                raise RuntimeError("A run is already in progress")

            settings = get_settings()
            if options.cap is not None:
                settings.application.daily_cap = options.cap
            if options.threshold is not None:
                settings.application.match_score_threshold = options.threshold

            problems = settings.validate_required()
            if problems:
                raise ValueError("; ".join(problems))

            session_factory = await self._ensure_db(settings)
            agent = create_agent(settings, session_factory, progress_reporter=self._event_bus)

            self._state = _RunState(
                agent=agent,
                dry_run=options.dry_run,
                phase="starting",
            )

            async def _run_wrapper() -> None:
                try:
                    await agent.run(dry_run=options.dry_run)
                except Exception as exc:
                    self._state.error = str(exc)
                    raise
                finally:
                    self._state.run_id = agent._run_log_id
                    self._state.counters = {
                        "jobs_found": agent._jobs_found,
                        "jobs_applied": agent._jobs_applied,
                        "jobs_skipped": agent._jobs_skipped,
                        "jobs_failed": agent._jobs_failed,
                    }
                    if getattr(agent, "_run_errored", False) and not self._state.error:
                        self._state.error = "Run failed — see agent logs for details"

            self._state.task = asyncio.create_task(_run_wrapper())

            # Wait briefly for run_log_id to be assigned
            for _ in range(50):
                if agent._run_log_id is not None:
                    break
                await asyncio.sleep(0.1)

            self._state.run_id = agent._run_log_id
            return self.get_status()

    async def stop(self) -> RunStatus:
        agent = self._state.agent
        if agent is not None:
            agent._interrupted = True
        return self.get_status()

    async def subscribe_events(self, run_id: int) -> AsyncIterator[dict]:
        queue = self._event_bus.subscribe(run_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            self._event_bus.unsubscribe(run_id, queue)
