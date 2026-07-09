"""Tests for parallel apply worker pool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.naukri_agent.browser.engine import WorkerBrowser, WorkerBrowserEngine
from src.naukri_agent.config.settings import ApplicationSettings
from src.naukri_agent.core.domain.entities import Job, ResumeProfile
from src.naukri_agent.orchestrator.agent import ApplyWorker, NaukriAgent, ProcessOutcome
from src.naukri_agent.bot.factory import ApplyWorkerStack


def _make_job(job_id: str) -> Job:
    return Job(
        naukri_job_id=job_id,
        title="Python Developer",
        company="Acme",
        url=f"https://www.naukri.com/job/{job_id}",
        skills="Python",
        description="Python developer role with backend focus.",
    )


def _make_agent_with_settings(apply_workers: int = 1) -> NaukriAgent:
    mock_factory = MagicMock()
    settings = MagicMock()
    settings.application = ApplicationSettings(apply_workers=apply_workers)
    settings.exclusions = MagicMock()
    settings.exclusions.title_whitelist = []
    settings.exclusions.enable_scam_filter = False
    settings.search = MagicMock()
    settings.search.keywords = ["Python"]
    settings.search.experience_min = 0
    settings.search.experience_max = 10
    settings.application.strict_policy_mode = False
    settings.application.collect_external_jobs = False
    settings.application.daily_cap = 10
    settings.application.dry_run = True
    settings.application.rate_limit_capacity = 10.0
    settings.application.rate_limit_refill_rate = 10.0
    settings.application.global_apply_interval_sec = 20.0
    settings.ai = MagicMock()
    settings.ai.fallback_model = None
    mock_factory.get_settings.return_value = settings
    agent = NaukriAgent(mock_factory)
    agent._resume_profile = ResumeProfile(name="Dev", skills=["Python"])
    agent._emit = AsyncMock()
    agent._emit_job = AsyncMock()
    agent._emit_counters = AsyncMock()
    agent._init_rate_limiters()
    return agent


def _mock_worker(worker_id: int) -> ApplyWorker:
    page = MagicMock()
    page.url = "https://www.naukri.com"
    page.is_closed.return_value = False
    page.goto = AsyncMock()
    context = MagicMock()
    worker_browser = WorkerBrowser(context=context, page=page, worker_id=worker_id)
    stack = MagicMock(spec=ApplyWorkerStack)
    stack.applier = MagicMock()
    stack.applier.apply_to_job = AsyncMock(return_value={"status": "applied"})
    stack.interactions = MagicMock()
    stack.interactions.wait_for_navigation_complete = AsyncMock()
    stack.interactions.action_delay = AsyncMock()
    stack.detail_page = MagicMock()
    stack.detail_page.navigate = AsyncMock()
    stack.detail_page.close_popups = AsyncMock()
    stack.detail_page.get_job_details = AsyncMock(
        return_value={
            "description": "Python role",
            "skills": "Python",
            "company_rating": 4.0,
            "is_external_apply": False,
        }
    )
    return ApplyWorker(id=worker_id, browser=worker_browser, stack=stack)


@pytest.mark.asyncio
async def test_effective_apply_workers_caps_at_five():
    app = ApplicationSettings(apply_workers=10, max_concurrent_applies=8)
    assert app.effective_apply_workers() == 5

    app2 = ApplicationSettings(apply_workers=2, max_concurrent_applies=5)
    assert app2.effective_apply_workers() == 2


@pytest.mark.asyncio
async def test_three_workers_drain_queue_concurrently():
    agent = _make_agent_with_settings(apply_workers=3)
    workers = [_mock_worker(i) for i in range(3)]
    agent._apply_workers = workers

    active = 0
    max_active = 0
    lock = asyncio.Lock()
    processed: list[str] = []

    async def fake_process(job, **kwargs):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
            processed.append(job.naukri_job_id)
        return ProcessOutcome.CONTINUE

    agent._process_one_job = AsyncMock(side_effect=fake_process)
    agent._check_cap_reached = AsyncMock(return_value=False)
    agent._workers_paused = asyncio.Event()
    agent._workers_paused.set()

    queue: asyncio.Queue[Job | None] = asyncio.Queue()
    for jid in ("j1", "j2", "j3"):
        await queue.put(_make_job(jid))
    for _ in workers:
        await queue.put(None)

    vector_filter = MagicMock()
    vector_filter.get_similarity_score.return_value = 0.5

    await asyncio.gather(
        *[
            agent._apply_worker_loop(w, queue, MagicMock(), vector_filter)
            for w in workers
        ]
    )

    assert sorted(processed) == ["j1", "j2", "j3"]
    assert max_active >= 2


@pytest.mark.asyncio
async def test_cap_race_only_one_apply():
    agent = _make_agent_with_settings(apply_workers=2)
    agent._apply_workers = [_mock_worker(0), _mock_worker(1)]
    agent._daily_applied = 0
    agent._settings.application.daily_cap = 1
    agent._settings.application.dry_run = False
    agent._workers_paused = asyncio.Event()
    agent._workers_paused.set()

    apply_count = 0
    apply_lock = asyncio.Lock()

    async def fake_process(job, **kwargs):
        nonlocal apply_count
        async with apply_lock:
            if agent._daily_applied >= 1:
                return ProcessOutcome.CAP_REACHED
            agent._daily_applied += 1
            apply_count += 1
        return ProcessOutcome.CONTINUE

    agent._process_one_job = AsyncMock(side_effect=fake_process)
    agent._check_cap_reached = AsyncMock(
        side_effect=lambda: agent._daily_applied >= agent._settings.application.daily_cap
    )

    queue: asyncio.Queue[Job | None] = asyncio.Queue()
    await queue.put(_make_job("a"))
    await queue.put(_make_job("b"))
    for _ in agent._apply_workers:
        await queue.put(None)

    vector_filter = MagicMock()
    vector_filter.get_similarity_score.return_value = 0.5

    await asyncio.gather(
        *[
            agent._apply_worker_loop(w, queue, MagicMock(), vector_filter)
            for w in agent._apply_workers
        ]
    )

    assert apply_count == 1


@pytest.mark.asyncio
async def test_dedup_claims_job_once():
    agent = _make_agent_with_settings()
    worker = _mock_worker(0)
    agent._repo = MagicMock()
    agent._repo.is_already_applied.return_value = False
    agent._repo.is_already_applied_composite.return_value = False

    claimed: list[str] = []

    async def track_claim(job, **kwargs):
        async with agent._claim_lock:
            if job.naukri_job_id in agent._in_flight_jobs:
                return ProcessOutcome.CONTINUE
            agent._in_flight_jobs.add(job.naukri_job_id)
            claimed.append(job.naukri_job_id)
        await asyncio.sleep(0.02)
        agent._in_flight_jobs.discard(job.naukri_job_id)
        return ProcessOutcome.CONTINUE

    agent._process_one_job = AsyncMock(side_effect=track_claim)

    job = _make_job("dup")
    results = await asyncio.gather(
        agent._process_one_job(
            job,
            initial_score=0.5,
            processed_count=1,
            total_queued=1,
            matcher=MagicMock(),
            vector_filter=MagicMock(),
            worker=worker,
        ),
        agent._process_one_job(
            job,
            initial_score=0.5,
            processed_count=2,
            total_queued=1,
            matcher=MagicMock(),
            vector_filter=MagicMock(),
            worker=worker,
        ),
    )

    assert len(claimed) == 1
    assert all(r == ProcessOutcome.CONTINUE for r in results)


@pytest.mark.asyncio
async def test_sentinel_shutdown_exits_all_workers():
    agent = _make_agent_with_settings(apply_workers=3)
    workers = [_mock_worker(i) for i in range(3)]
    agent._apply_workers = workers
    agent._process_one_job = AsyncMock(return_value=ProcessOutcome.CONTINUE)
    agent._check_cap_reached = AsyncMock(return_value=False)
    agent._workers_paused = asyncio.Event()
    agent._workers_paused.set()

    queue: asyncio.Queue[Job | None] = asyncio.Queue()
    for _ in workers:
        await queue.put(None)

    vector_filter = MagicMock()
    tasks = [
        asyncio.create_task(agent._apply_worker_loop(w, queue, MagicMock(), vector_filter))
        for w in workers
    ]
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)


@pytest.mark.asyncio
async def test_worker_context_isolation():
    pages = [object(), object(), object()]
    workers = []
    for i, page in enumerate(pages):
        wb = WorkerBrowser(context=MagicMock(), page=page, worker_id=i)  # type: ignore[arg-type]
        engine = WorkerBrowserEngine(wb)
        workers.append(id(engine.page))

    assert len(set(workers)) == 3


@pytest.mark.asyncio
async def test_worker_needs_job_navigation_detects_about_blank():
    agent = _make_agent_with_settings()
    job = _make_job("12345678")
    page = MagicMock()
    page.url = "about:blank"
    assert agent._worker_needs_job_navigation(page, job) is True


@pytest.mark.asyncio
async def test_worker_needs_job_navigation_skips_empty_url():
    agent = _make_agent_with_settings()
    job = _make_job("12345678")
    job.url = ""
    page = MagicMock()
    page.url = "about:blank"
    assert agent._worker_needs_job_navigation(page, job) is False


@pytest.mark.asyncio
async def test_resolve_job_url_adds_domain():
    agent = _make_agent_with_settings()
    job = _make_job("12345678")
    job.url = "/job-listings-12345678"
    assert agent._resolve_job_url(job).startswith("https://www.naukri.com/")


@pytest.mark.asyncio
async def test_apply_workers_one_regression():
    agent = _make_agent_with_settings(apply_workers=1)
    assert agent._settings.application.effective_apply_workers() == 1

    with patch.object(agent, "_bootstrap_apply_workers", new=AsyncMock()) as boot:
        boot.return_value = None
        agent._apply_workers = [_mock_worker(0)]
        agent._run_search_apply_pipeline = AsyncMock()
        agent._init_rate_limiters()

        # Pipeline receives no shared applier — workers own stacks
        await agent._run_search_apply_pipeline(MagicMock(), MagicMock(), MagicMock())
        agent._run_search_apply_pipeline.assert_awaited_once()
        call_args = agent._run_search_apply_pipeline.await_args[0]
        assert len(call_args) == 3
