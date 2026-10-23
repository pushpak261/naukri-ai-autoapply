"""Real Chromium regression coverage for Naukri's HTTP-200 error screen."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from playwright.async_api import Error, async_playwright

from src.naukri_agent.browser.pages.search import SearchPage
from src.naukri_agent.browser.search import JobSearcher
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.utils.exceptions import SearchAccessError, SearchLoadError
from src.naukri_agent.utils.helpers import build_search_url

ERROR_HTML = "<h1>Oops! Something went wrong</h1><p>There was an error loading the page. Please reload to view the content</p><button>Reload</button>"
RESULT_HTML = """<article class="jobTuple">
<a class="title" href="https://www.naukri.com/job-java-123456789012">Java Developer</a>
<span class="comp-name">Employer</span><span class="exp-wrap">0-2 Yrs</span>
<span class="job-post-day">Today</span><span class="tag-li">Java</span></article>"""


@pytest_asyncio.fixture
async def search_page():
    async with async_playwright() as runtime:
        try:
            browser = await runtime.chromium.launch()
        except Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("Chromium required for search page regressions")
            raise
        try:
            page = await browser.new_page()
            engine = SimpleNamespace(page=page, is_alive=lambda: True)
            yield SearchPage(engine, AsyncMock()), engine
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_error_screen_retries_without_sort_and_keeps_query_filters(
    search_page, tmp_path, monkeypatch
):
    search, engine = search_page
    requests = []

    async def serve(route):
        requests.append(route.request.url)
        body = ERROR_HTML if "sort" in parse_qs(urlsplit(route.request.url).query) else RESULT_HTML
        await route.fulfill(status=200, content_type="text/html", body=body)

    await engine.page.route("**/*", serve)
    monkeypatch.setattr("src.naukri_agent.browser.pages.search.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("src.naukri_agent.browser.search.random_delay", AsyncMock())
    settings = Settings(
        project_root=tmp_path, search={"sort_by": "date", "experience_max": 2, "freshness": 14}
    )
    worker = JobSearcher(search, AsyncMock(), engine, settings)
    jobs = await worker._search_keyword_location("Java", "Pune", 1)
    assert [job.naukri_job_id for job in jobs] == ["123456789012"]
    assert len(requests) == 2
    first, retry = [parse_qs(urlsplit(url).query) for url in requests]
    assert first.pop("sort") == ["f"]
    assert retry == first
    assert worker.total_found == 1


@pytest.mark.asyncio
async def test_permanent_render_error_is_failure_after_three_attempts(search_page, monkeypatch):
    search, engine = search_page
    calls = []

    async def serve(route):
        calls.append(route.request.url)
        await route.fulfill(status=200, content_type="text/html", body=ERROR_HTML)

    await engine.page.route("**/*", serve)
    monkeypatch.setattr("src.naukri_agent.browser.pages.search.asyncio.sleep", AsyncMock())
    with pytest.raises(SearchLoadError, match="failed after 3 attempts"):
        await search.navigate_to_search(build_search_url("Java", "Pune"))
    assert len(calls) == 3
    with pytest.raises(SearchLoadError, match="page-load error"):
        await search.parse_job_cards()
    assert not await search.has_no_results()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body",
    [(403, "Access Denied"), (429, "Too many requests"), (200, "Verify you are human")],
)
async def test_access_challenges_stop_without_retries(search_page, status, body):
    search, engine = search_page
    calls = []

    async def serve(route):
        calls.append(route.request.url)
        await route.fulfill(status=status, content_type="text/html", body=body)

    await engine.page.route("**/*", serve)
    with pytest.raises(SearchAccessError):
        await search.navigate_to_search(build_search_url("Java", "Pune"))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_explicit_empty_results_are_not_a_failure(search_page):
    search, engine = search_page
    await engine.page.route(
        "**/*",
        lambda route: route.fulfill(
            status=200, content_type="text/html", body="<h1>No matching jobs found</h1>"
        ),
    )
    await search.navigate_to_search(build_search_url("Java", "Pune"))
    assert await search.has_no_results()
    assert await search.parse_job_cards() == []


@pytest.mark.asyncio
async def test_slow_results_wait_for_render_instead_of_returning_empty(search_page):
    search, engine = search_page
    html = (
        '<main>Loading jobs...</main><script>setTimeout(() => document.querySelector("main").innerHTML = '
        + repr(RESULT_HTML)
        + ", 300)</script>"
    )
    await engine.page.route(
        "**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html)
    )
    await search.navigate_to_search(build_search_url("Java", "Pune"))
    assert not await search.has_no_results()
    assert len(await search.parse_job_cards()) == 1


@pytest.mark.asyncio
async def test_repeated_failed_queries_end_discovery_with_error(tmp_path):
    worker = JobSearcher(
        AsyncMock(),
        AsyncMock(),
        SimpleNamespace(is_alive=lambda: True),
        Settings(
            project_root=tmp_path,
            search={"keywords": ["Java"], "locations": ["Pune", "Mumbai", "Bengaluru"]},
        ),
    )
    worker._search_keyword_location = AsyncMock(side_effect=SearchLoadError("Render failed"))
    with pytest.raises(SearchLoadError, match="consecutive searches"):
        await worker.search_all()
    assert worker._search_keyword_location.await_count == 2
    assert len(worker.failed_searches) == 2


@pytest.mark.asyncio
async def test_search_access_failure_never_advances_to_next_query(tmp_path):
    worker = JobSearcher(
        AsyncMock(),
        AsyncMock(),
        SimpleNamespace(is_alive=lambda: True),
        Settings(
            project_root=tmp_path, search={"keywords": ["Java"], "locations": ["Pune", "Mumbai"]}
        ),
    )
    worker._search_keyword_location = AsyncMock(side_effect=SearchAccessError("Verify sign-in"))
    with pytest.raises(SearchAccessError):
        await worker.search_all()
    worker._search_keyword_location.assert_awaited_once()
