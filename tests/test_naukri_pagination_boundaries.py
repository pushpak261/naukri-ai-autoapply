"""Naukri's last result and silent page resets bound each query."""

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.naukri_agent.browser.search import JobSearcher
from src.naukri_agent.config.settings import Settings
from tests.test_naukri_search_loading import search_page as search_page


def result(identifier, count, title="Java Developer"):
    return f"""<div>{count}</div><article class="jobTuple">
      <a class="title" href="https://www.naukri.com/job-java-{identifier}">{title}</a>
      <span class="exp-wrap">0-2 Yrs</span><span class="job-post-day">Today</span></article>"""


@pytest.mark.asyncio
@pytest.mark.parametrize("reset", [True, False])
async def test_stops_before_out_of_range_or_reset_results(
    search_page, tmp_path, monkeypatch, reset
):
    search, engine = search_page
    requests = []

    async def serve(route):
        number = int(parse_qs(urlsplit(route.request.url).query).get("pageNo", ["1"])[0])
        requests.append(number)
        body = (
            result("123456789001", "1 - 20 of 21")
            if number == 1
            else result(
                "123456789002",
                "1 - 20 of 4,000" if reset else "21 - 21 of 21",
                "Sales Manager" if reset else "Java Developer",
            )
        )
        await route.fulfill(content_type="text/html", body=body)

    await engine.page.route("**/*", serve)
    monkeypatch.setattr("src.naukri_agent.browser.search.random_delay", AsyncMock())
    worker = JobSearcher(search, AsyncMock(), engine, Settings(project_root=tmp_path))
    jobs = await worker._search_keyword_location("Java", "Pune", 15)
    assert requests == [1, 2]
    assert [j.naukri_job_id for j in jobs] == (
        ["123456789001"] if reset else ["123456789001", "123456789002"]
    )
    assert len(worker.failed_searches) == int(reset)


@pytest.mark.asyncio
async def test_result_range_uses_visible_metadata_not_card_text(search_page):
    search, engine = search_page
    await engine.page.set_content(
        "<span hidden>1 - 20 of 900</span><article>1 - 20 of 600</article><div>1 – 20 of 2,001</div>"
    )
    assert await search.result_window() == {"start": 1, "end": 20, "total": 2001}
    await engine.page.set_content("<main>No counter is rendered</main>")
    assert await search.result_window() is None
