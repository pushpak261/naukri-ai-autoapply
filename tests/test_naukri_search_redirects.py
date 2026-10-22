"""Search canonicalization must preserve results without accepting query resets."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.naukri_agent.browser.search import JobSearcher, _same_search_page
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job
from src.naukri_agent.utils.helpers import build_search_url


@pytest.mark.parametrize(
    "actual,accepted",
    [
        ("https://www.naukri.com/java-jobs-in-pune-2", True),
        ("https://naukri.com/java-jobs-in-pune-2/", True),
        ("https://www.naukri.com/java-jobs-in-pune-2?k=Java&l=Pune&pageNo=2", True),
        ("https://www.naukri.com/java-jobs-in-pune-2?k=Python", False),
        ("https://www.naukri.com/java-jobs-in-pune-2?l=Mumbai", False),
        ("https://www.naukri.com/java-jobs-in-pune-2?pageNo=1", False),
        ("https://www.naukri.com/java-jobs-in-pune-2?k=", False),
        ("https://www.naukri.com/java-jobs-in-pune", False),
        ("https://www.naukri.com/python-jobs-in-pune-2", False),
        ("https://www.naukri.com/nlogin/login?k=Java", False),
        ("https://example.invalid/java-jobs-in-pune-2?k=Java", False),
        ("http://www.naukri.com/java-jobs-in-pune-2", False),
    ],
)
def test_search_redirect_context(actual, accepted):
    assert _same_search_page(build_search_url("Java", "Pune", page=2), actual) is accepted


def listing(identifier, experience="0-2 Yrs", posted="Today"):
    return Job(
        identifier,
        "Java Developer",
        "Example",
        f"https://www.naukri.com/job-{identifier}",
        experience=experience,
        posted_date=posted,
    )


@pytest.mark.asyncio
async def test_canonical_pages_are_parsed_filtered_and_deduplicated(tmp_path, monkeypatch):
    search = AsyncMock()
    engine = MagicMock()

    async def canonicalize(url):
        engine.page.url = url.split("?", 1)[0]

    search.navigate_to_search.side_effect = canonicalize
    search.has_no_results.return_value = False
    first, second = listing("123456789001"), listing("123456789002")
    search.parse_job_cards.side_effect = [
        [first],
        [
            first,
            second,
            listing("123456789003", experience="8-10 Yrs"),
            listing("123456789004", posted="30 days ago"),
        ],
        [second],  # Repeated results must terminate pagination, not loop.
    ]
    settings = Settings(project_root=tmp_path, search={"experience_max": 2, "freshness": 7})
    worker = JobSearcher(search, AsyncMock(), engine, settings)
    monkeypatch.setattr("src.naukri_agent.browser.search.random_delay", AsyncMock())

    jobs = await worker._search_keyword_location("Java", "Pune", 5)

    assert {job.naukri_job_id for job in jobs} == {first.naukri_job_id, second.naukri_job_id}
    assert worker.total_found == 2
    assert search.navigate_to_search.await_count == 3


@pytest.mark.asyncio
async def test_redirected_search_keeps_earlier_results_but_never_parses_login(
    tmp_path, monkeypatch
):
    search = AsyncMock()
    engine = MagicMock()
    count = 0

    async def navigate(url):
        nonlocal count
        count += 1
        engine.page.url = url if count == 1 else "https://www.naukri.com/nlogin/login?k=Java"

    search.navigate_to_search.side_effect = navigate
    search.has_no_results.return_value = False
    first = listing("123456789001")
    search.parse_job_cards.return_value = [first]
    worker = JobSearcher(search, AsyncMock(), engine, Settings(project_root=tmp_path))
    monkeypatch.setattr("src.naukri_agent.browser.search.random_delay", AsyncMock())

    assert await worker._search_keyword_location("Java", "Pune", 3) == [first]
    search.parse_job_cards.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_canonical_page_finishes_without_parsing(tmp_path, monkeypatch):
    search = AsyncMock()
    engine = MagicMock()
    engine.page.url = "https://www.naukri.com/java-jobs-in-pune"
    search.has_no_results.return_value = True
    worker = JobSearcher(search, AsyncMock(), engine, Settings(project_root=tmp_path))
    monkeypatch.setattr("src.naukri_agent.browser.search.random_delay", AsyncMock())

    assert await worker._search_keyword_location("Java", "Pune", 3) == []
    search.parse_job_cards.assert_not_awaited()
