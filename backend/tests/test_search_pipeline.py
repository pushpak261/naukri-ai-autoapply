"""Tests for pipelined search-and-apply orchestration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.naukri_agent.utils.similarity import VectorSimilarityFilter
from src.naukri_agent.browser.gate import BrowserGate
from src.naukri_agent.browser.search import SearchBatch
from src.naukri_agent.core.domain.entities import Job, ResumeProfile
from src.naukri_agent.orchestrator.agent import NaukriAgent, ProcessOutcome


def _make_job(job_id: str, title: str = "Developer") -> Job:
    return Job(
        naukri_job_id=job_id,
        title=title,
        company="Acme",
        url=f"https://www.naukri.com/job/{job_id}",
        skills="Python",
    )


async def _async_batch_iter(batches: list[SearchBatch]):
    for batch in batches:
        yield batch


@pytest.mark.asyncio
async def test_rank_batch_jobs_orders_by_similarity():
    mock_factory = MagicMock()
    mock_factory.get_settings.return_value = MagicMock()
    agent = NaukriAgent(mock_factory)

    jobs = [
        _make_job("low", title="Unrelated Role"),
        _make_job("high", title="Python Developer"),
    ]
    vector_filter = VectorSimilarityFilter(["Python", "Developer"])

    ranked = agent._rank_batch_jobs(jobs, vector_filter)

    assert ranked[0].naukri_job_id == "high"
    assert ranked[1].naukri_job_id == "low"


@pytest.mark.asyncio
async def test_search_producer_enqueues_ranked_jobs_per_batch():
    mock_factory = MagicMock()
    settings = MagicMock()
    settings.application.daily_cap = 10
    mock_factory.get_settings.return_value = settings

    agent = NaukriAgent(mock_factory)
    agent._resume_profile = ResumeProfile(name="Dev", skills=["Python"])
    agent._emit = AsyncMock()
    agent._emit_job = AsyncMock()
    agent._emit_counters = AsyncMock()

    batch_one = SearchBatch(
        keyword="Software Engineer",
        location="Pune",
        jobs=[_make_job("job_b", title="Java Dev"), _make_job("job_a", title="Python Dev")],
    )
    batch_two = SearchBatch(
        keyword="Software Engineer",
        location="Mumbai",
        jobs=[_make_job("job_c", title="Python Engineer")],
    )

    searcher = MagicMock()
    searcher.iter_search_batches = MagicMock(
        return_value=_async_batch_iter([batch_one, batch_two])
    )

    queue: asyncio.Queue[Job | None] = asyncio.Queue()
    gate = BrowserGate()
    vector_filter = VectorSimilarityFilter(["Python"])

    await agent._search_producer(searcher, queue, gate, vector_filter)

    enqueued: list[str] = []
    while not queue.empty():
        job = queue.get_nowait()
        if job is not None:
            enqueued.append(job.naukri_job_id)

    assert enqueued == ["job_a", "job_b", "job_c"]
    assert agent._jobs_found == 3
    assert agent._total_queued == 3
    assert agent._phase == "processing"

    event_types = [call.args[0] for call in agent._emit.await_args_list]
    assert "search_batch_completed" in event_types
    assert "search_completed" in event_types


@pytest.mark.asyncio
async def test_pipeline_consumer_starts_while_producer_searches_next_batch():
    mock_factory = MagicMock()
    settings = MagicMock()
    settings.application.daily_cap = 10
    mock_factory.get_settings.return_value = settings

    agent = NaukriAgent(mock_factory)
    agent._resume_profile = ResumeProfile(name="Dev", skills=["Python"])
    agent._emit = AsyncMock()
    agent._emit_job = AsyncMock()
    agent._emit_counters = AsyncMock()

    first_batch_ready = asyncio.Event()
    consumer_started = asyncio.Event()
    release_second_batch = asyncio.Event()

    async def slow_iter_batches(browser_gate=None):
        yield SearchBatch(
            keyword="Software Engineer",
            location="Pune",
            jobs=[_make_job("job_1")],
        )
        first_batch_ready.set()
        await release_second_batch.wait()
        yield SearchBatch(
            keyword="Software Engineer",
            location="Mumbai",
            jobs=[_make_job("job_2")],
        )

    searcher = MagicMock()
    searcher.iter_search_batches = slow_iter_batches

    queue: asyncio.Queue[Job | None] = asyncio.Queue()
    gate = BrowserGate()
    vector_filter = MagicMock(spec=VectorSimilarityFilter)
    vector_filter.get_similarity_score.return_value = 0.5

    async def fake_process_one_job(*args, **kwargs):
        consumer_started.set()
        return ProcessOutcome.CONTINUE

    agent._process_one_job = AsyncMock(side_effect=fake_process_one_job)

    producer_task = asyncio.create_task(
        agent._search_producer(searcher, queue, gate, vector_filter)
    )

    await asyncio.wait_for(first_batch_ready.wait(), timeout=2)
    consumer_task = asyncio.create_task(
        agent._apply_consumer(
            queue,
            MagicMock(),
            MagicMock(),
            searcher,
            vector_filter,
            gate,
        )
    )

    await asyncio.wait_for(consumer_started.wait(), timeout=2)
    assert agent._process_one_job.await_count >= 1

    release_second_batch.set()
    await producer_task
    await consumer_task


@pytest.mark.asyncio
async def test_browser_gate_serializes_concurrent_holders():
    gate = BrowserGate()
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal active, max_active
        async with gate.hold():
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1

    await asyncio.gather(*(worker() for _ in range(5)))
    assert max_active == 1


@pytest.mark.asyncio
async def test_iter_search_batches_deduplicates_across_batches():
    from src.naukri_agent.browser.search import JobSearcher

    search_page = AsyncMock()
    search_page.navigate_to_search = AsyncMock()
    search_page.close_popups = AsyncMock()
    search_page.has_no_results = AsyncMock(return_value=False)
    search_page.scroll_to_load = AsyncMock()
    search_page.parse_job_cards = AsyncMock(
        side_effect=[
            [_make_job("dup"), _make_job("unique_a")],
            [_make_job("dup"), _make_job("unique_b")],
        ]
    )

    settings = MagicMock()
    settings.search.keywords = ["Python"]
    settings.search.locations = ["Pune", "Mumbai"]
    settings.search.max_pages = 1
    settings.search.experience_min = 0
    settings.search.experience_max = 4
    settings.search.salary_min = 0
    settings.search.freshness = 7
    settings.search.sort_by = "relevance"
    settings.application.min_company_rating = 0

    engine = MagicMock()
    engine.is_alive.return_value = True

    searcher = JobSearcher(
        search_page=search_page,
        detail_page=AsyncMock(),
        engine=engine,
        settings=settings,
    )

    batches: list[SearchBatch] = []
    with patch("src.naukri_agent.browser.search.random_delay", new=AsyncMock()):
        async for batch in searcher.iter_search_batches():
            batches.append(batch)

    assert len(batches) == 2
    assert [job.naukri_job_id for job in batches[0].jobs] == ["dup", "unique_a"]
    assert [job.naukri_job_id for job in batches[1].jobs] == ["unique_b"]
