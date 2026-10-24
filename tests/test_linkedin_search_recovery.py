"""Location changes keep the requested filters; access blocks stop discovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.linked_agent.browser.search import LinkedInJobSearcher
from src.linked_agent.config.settings import Settings
from src.linked_agent.utils.exceptions import LoginError, RateLimitError
from tests.test_linkedin_modern_search import search_page as search_page


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.linkedin.com/jobs/view/123/", True),
        ("https://www.linkedin.com/jobs/view/java-developer-at-employer-123/", True),
        ("https://www.linkedin.com/jobs/search/?currentJobId=123", True),
        ("https://www.linkedin.com/jobs/search/?currentJobId=999", False),
        ("https://www.linkedin.com/jobs/view/999/", False),
        ("https://example.invalid/jobs/view/123/", False),
    ],
)
def test_selected_listing_must_match_the_job_being_evaluated(url, expected):
    from src.linked_agent.bot.agent import _matches_job_url

    assert _matches_job_url(url, "123") is expected


def test_linkedin_file_logging_is_added_once_when_shared_logger_exists(tmp_path):
    import logging
    from src.linked_agent.utils.logger import setup_logging

    root = logging.getLogger()
    before = set(root.handlers)
    level = root.level
    try:
        setup_logging(log_dir=str(tmp_path))
        setup_logging(log_dir=str(tmp_path))
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1
        logging.getLogger("linked_agent").info("LinkedIn flow test")
        added[0].flush()
        assert "LinkedIn flow test" in (tmp_path / "linkedin_agent.log").read_text()
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)


@pytest.mark.asyncio
async def test_nested_location_picker_ignores_hidden_copy_and_keeps_filters(search_page):
    search, page = search_page
    destination = "https://www.linkedin.com/jobs/search-results/?geoId=106164952"
    visited = []

    async def serve(route):
        visited.append(route.request.url)
        await route.fulfill(body='<div aria-label="Location Mumbai">Mumbai</div>')

    await page.route("https://www.linkedin.com/jobs/search-results/**", serve)
    await page.set_content(
        f"""<div hidden><div aria-label="Location Old city">Old city</div></div>
      <button onclick="document.querySelector('[contenteditable]').style.display='block'">
      <span><span aria-label="Location Pune">Pune</span></span></button>
      <div contenteditable="true" aria-label="Location" style="display:none">Pune</div>
      <div id="semanticSearchBoxLocationList"><a href="{destination}">Mumbai</a></div>"""
    )
    search._requested_search_params = {
        "keywords": ["Java Developer"],
        "f_E": ["1,2"],
        "f_TPR": ["604800"],
        "f_AL": ["true"],
    }
    await search._ensure_search_location("Mumbai")
    query = parse_qs(urlsplit(visited[-1]).query)
    assert query == {**search._requested_search_params, "geoId": ["106164952"]}
    assert search._resolved_location_ids["Mumbai"] == "106164952"


@pytest.mark.asyncio
async def test_http_rate_limit_stops_without_retrying(search_page):
    search, page = search_page
    requests = []

    async def serve(route):
        requests.append(route.request.url)
        await route.fulfill(status=429, body="Please slow down")

    await page.route("**/*", serve)
    with pytest.raises(RateLimitError):
        await search.navigate_to_search("https://www.linkedin.com/jobs/search/?keywords=Java")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_verified_location_cache_survives_a_restart(search_page, tmp_path, monkeypatch):
    import json
    from src.linked_agent.browser.pages.search import LinkedInSearchPage

    search, page = search_page
    search._engine._settings = SimpleNamespace(project_root=tmp_path)
    search._remember_location("Pune", "114806696")
    path = tmp_path / "data/linkedin/search_locations.json"
    assert json.loads(path.read_text()) == {"Pune": "114806696"}
    resumed = LinkedInSearchPage(search._engine, AsyncMock())
    visited = []

    async def serve(route):
        visited.append(route.request.url)
        await route.fulfill(body='<div aria-label="Location Pune">Pune</div>')

    await page.route("**/*", serve)
    monkeypatch.setattr("src.linked_agent.browser.pages.search.asyncio.sleep", AsyncMock())
    await resumed.navigate_to_search(
        "https://www.linkedin.com/jobs/search/?keywords=Java&location=Pune&f_E=1,2"
    )
    query = parse_qs(urlsplit(visited[-1]).query)
    assert query["geoId"] == ["114806696"]
    assert query["f_E"] == ["1,2"]
    assert query["keywords"] == ["Java"]


@pytest.mark.asyncio
async def test_expired_session_is_not_swallowed_or_reported_as_no_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.linked_agent.browser.search.asyncio.get_event_loop",
        lambda: SimpleNamespace(time=lambda: 1),
    )
    engine = SimpleNamespace(
        page=SimpleNamespace(url="https://www.linkedin.com/checkpoint/challenge")
    )
    worker = LinkedInJobSearcher(AsyncMock(), AsyncMock(), engine, Settings(project_root=tmp_path))
    with pytest.raises(LoginError):
        await worker._check_session_health()
    search = AsyncMock()
    search.navigate_to_search.side_effect = LoginError("Sign in required")
    worker = LinkedInJobSearcher(search, AsyncMock(), engine, Settings(project_root=tmp_path))
    with pytest.raises(LoginError):
        await worker._search_keyword("Java", "Pune")


def test_location_cache_storage_failure_keeps_verified_in_memory(tmp_path, monkeypatch):
    from pathlib import Path
    from src.linked_agent.browser.pages.search import LinkedInSearchPage

    search = LinkedInSearchPage(
        SimpleNamespace(_settings=SimpleNamespace(project_root=tmp_path)), AsyncMock()
    )
    monkeypatch.setattr(Path, "mkdir", MagicMock(side_effect=OSError("Read-only storage")))
    search._remember_location("Pune", "114806696")
    assert search._location_ids() == {"Pune": "114806696"}


@pytest.mark.parametrize(
    "question,expected",
    [
        ("How many years of professional experience do you have with Java?", "1"),
        ("How many months of professional experience do you have with Java?", "12"),
        ("Do you have at least 2 years of Java experience?", "No"),
    ],
)
def test_experience_counts_are_not_confused_with_boolean_questions(tmp_path, question, expected):
    from libs.common.screening import evidence_answer
    from src.linked_agent.models.entities import ResumeProfile

    settings = Settings(project_root=tmp_path, profile={"skill_experience_years": {"Java": 1}})
    candidate = ResumeProfile(skills=["Java"], total_experience_years=1)
    assert (
        evidence_answer({"question": question, "field_type": "text"}, settings, candidate)
        == expected
    )
