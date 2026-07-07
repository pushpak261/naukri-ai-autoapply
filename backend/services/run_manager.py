"""Manages a single active agent run for the web API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.asyncio_windows import LoopBridgingProgressReporter, run_on_playwright_loop
from backend.schemas.run import RunCreate, RunStatus
from src.naukri_agent.config.settings import Settings, get_settings
from src.naukri_agent.core.progress import InMemoryEventBus
from src.naukri_agent.database.manager import DatabaseManager
from src.naukri_agent.main import create_agent
from src.naukri_agent.models.db_schema import setup_database_manager

if TYPE_CHECKING:
    from src.naukri_agent.bot.agent import NaukriAgent


@dataclass
class _RunState:
    task: asyncio.Task | None = None
    agent: NaukriAgent | None = None
    run_id: int | None = None
    dry_run: bool = False
    error: str | None = None
    phase: str = ""
    counters: dict = field(default_factory=dict)
    strict_policy_mode: bool = False
    experience_source: str = "config_default"


class RunManager:
    """Enforces one active agent run at a time."""

    def __init__(self) -> None:
        self._event_bus = InMemoryEventBus()
        self._state = _RunState()
        self._db_manager: DatabaseManager | None = None
        self._lock = asyncio.Lock()

    @property
    def event_bus(self) -> InMemoryEventBus:
        return self._event_bus

    async def _ensure_db(self, settings: Settings) -> DatabaseManager:
        if self._db_manager is None:
            self._db_manager = await setup_database_manager(settings.db_path)
        return self._db_manager

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
                strict_policy_mode=state.strict_policy_mode,
                experience_source=state.experience_source,
            )
        if state.task and state.task.done() and state.error:
            return RunStatus(
                run_id=state.run_id,
                status="error",
                phase="error",
                dry_run=state.dry_run,
                error=state.error,
                strict_policy_mode=state.strict_policy_mode,
                experience_source=state.experience_source,
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
                strict_policy_mode=state.strict_policy_mode,
                experience_source=state.experience_source,
                **state.counters,
            )
        return RunStatus(
            strict_policy_mode=state.strict_policy_mode,
            experience_source=state.experience_source,
        )

    async def start(self, options: RunCreate) -> RunStatus:
        async with self._lock:
            if self._state.task and not self._state.task.done():
                raise RuntimeError("A run is already in progress")

            base_settings = get_settings()
            settings = base_settings.copy_for_run(
                cap=options.cap,
                threshold=options.threshold,
                experience_min=options.experience_min,
                experience_max=options.experience_max,
            )
            experience_source = (
                "ui_override"
                if options.experience_min is not None or options.experience_max is not None
                else "config_default"
            )

            problems = settings.validate_required()
            if problems:
                raise ValueError("; ".join(problems))

            main_loop = asyncio.get_running_loop()
            progress = LoopBridgingProgressReporter(self._event_bus, main_loop)

            self._state = _RunState(
                dry_run=options.dry_run,
                phase="starting",
                strict_policy_mode=getattr(settings.application, "strict_policy_mode", False),
                experience_source=experience_source,
            )

            async def _agent_work() -> NaukriAgent:
                db_manager = await setup_database_manager(settings.db_path)
                agent = create_agent(settings, db_manager)
                if hasattr(agent, "set_progress_reporter"):
                    agent.set_progress_reporter(progress)
                self._state.agent = agent
                await agent.run(dry_run=options.dry_run)
                return agent

            async def _run_wrapper() -> None:
                try:
                    agent = await run_on_playwright_loop(_agent_work)
                    self._state.agent = agent
                except Exception as exc:
                    self._state.error = str(exc)
                    raise
                finally:
                    agent = self._state.agent
                    if agent is not None:
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
                agent = self._state.agent
                if agent is not None and agent._run_log_id is not None:
                    break
                await asyncio.sleep(0.1)

            agent = self._state.agent
            if agent is not None:
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
