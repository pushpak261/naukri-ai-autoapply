"""The component-based results layout must retain every job, not just the sidebar."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from playwright.async_api import Error, async_playwright

from src.linked_agent.browser.pages.search import LinkedInSearchPage


@pytest_asyncio.fixture
async def search_page():
    async with async_playwright() as runtime:
        try:
            browser = await runtime.chromium.launch(headless=True)
        except Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("Chromium is needed for modern LinkedIn layout regressions")
            raise
        try:
            tab = await browser.new_page()
            engine = MagicMock()
            engine.page = tab
            interactions = AsyncMock()
            interactions.element_exists.return_value = False
            yield LinkedInSearchPage(engine, interactions), tab
        finally:
            await browser.close()


def card(identifier, title, company, location):
    return f"""<div role="button" componentkey="job-card-component-ref-{identifier}">
    <div componentkey="job-card-component-ref-{identifier}"><p><span>{title} (Verified job)</span><span aria-hidden="true">{title}</span></p>
    <p>{company}</p><p>{location}</p><p>2 days ago</p><span>Easy Apply</span>
    <button aria-label="Dismiss {title} job">Dismiss</button></div></div>"""


@pytest.mark.asyncio
async def test_modern_button_cards_are_unique_and_have_complete_metadata(search_page):
    search, page = search_page
    await page.set_content(
        card("101", "Java Developer", "First Company", "Pune")
        + card("102", "Backend Engineer", "Second Company", "Mumbai")
    )
    raw = await search._extract_cards_from_dom(page)
    assert await search._safe_card_count(page) == 2
    assert [
        (item["linkedin_job_id"], item["title"], item["company"], item["location"]) for item in raw
    ] == [
        ("101", "Java Developer", "First Company", "Pune"),
        ("102", "Backend Engineer", "Second Company", "Mumbai"),
    ]
    assert raw[1]["url"] == "https://www.linkedin.com/jobs/view/102"
    assert raw[1]["easy_apply"] is True


@pytest.mark.asyncio
async def test_modern_pagination_button_advances_to_different_jobs(search_page, monkeypatch):
    search, page = search_page
    monkeypatch.setattr("src.linked_agent.browser.pages.search.asyncio.sleep", AsyncMock())
    await page.set_content(
        card("101", "Java Developer", "Company", "Pune")
        + """<button data-testid="pagination-controls-next-button-visible" onclick="document.querySelector('[role=button]').setAttribute('componentkey','job-card-component-ref-102')">Next</button>"""
    )
    assert await search.go_to_next_page()
    raw = await search._extract_cards_from_dom(page)
    assert raw[0]["linkedin_job_id"] == "102"


@pytest.mark.asyncio
async def test_modern_location_picker_replaces_silently_reused_city(search_page):
    search, page = search_page
    destination = "https://www.linkedin.com/jobs/search-results/?geoId=106164952"
    await page.route(
        destination,
        lambda route: route.fulfill(body='<div aria-label="Location Mumbai">Mumbai</div>'),
    )
    await page.set_content(
        """<div role="button" onclick="document.querySelector('[contenteditable]').style.display='block';document.querySelector('#semanticSearchBoxLocationList').style.display='block'">
    <div aria-label="Location Pune">Pune</div></div>
    <div contenteditable="true" aria-label="Location" style="display:none">Pune</div>
    <div id="semanticSearchBoxLocationList" style="display:none"><a href="https://www.linkedin.com/jobs/search-results/?geoId=106164952">Mumbai</a></div>"""
    )
    await search._ensure_search_location("Mumbai")
    assert await page.locator('[aria-label^="Location "]').inner_text() == "Mumbai"
    assert search._resolved_location_ids["Mumbai"] == "106164952"


@pytest.mark.asyncio
async def test_modern_remote_filter_uses_visible_label_for_hidden_input(search_page):
    search, page = search_page
    await page.set_content(
        """<div aria-label="Location Bengaluru">Bengaluru</div>
    <div hidden><input aria-label="Filter by Remote" type="checkbox"></div>
    <input id="remote" aria-label="Filter by Remote" type="checkbox" style="opacity:0;width:0;height:0">
    <label for="remote">Remote</label>"""
    )
    await search._ensure_search_location("Remote")
    assert await page.locator("#remote").is_checked()


@pytest.mark.asyncio
async def test_saved_session_is_verified_on_jobs_without_starting_password_login(
    search_page, monkeypatch
):
    from src.linked_agent.browser.login import LinkedInLoginHandler
    from src.linked_agent.browser.pages.login import LinkedInLoginPage

    search, page = search_page
    monkeypatch.setattr("src.linked_agent.browser.pages.login.asyncio.sleep", AsyncMock())
    await page.route(
        "https://www.linkedin.com/jobs/",
        lambda route: route.fulfill(body='<nav><a href="/mynetwork/">My Network</a></nav>'),
    )
    engine = search._engine
    engine.has_saved_session.return_value = True
    strategy = AsyncMock()
    handler = LinkedInLoginHandler(
        LinkedInLoginPage(engine, AsyncMock()), engine, strategy=strategy
    )
    assert await handler.login()
    strategy.authenticate.assert_not_awaited()
    engine.mark_session_authenticated.assert_called_once()


@pytest.mark.asyncio
async def test_remote_target_applies_work_filter_with_configured_country():
    from urllib.parse import parse_qs, urlparse
    from src.linked_agent.browser.search import LinkedInJobSearcher
    from src.linked_agent.config.settings import Settings

    settings = Settings(search={"remote_location": "India", "max_pages": 1})
    search = AsyncMock()
    search.has_no_results.return_value = True
    searcher = LinkedInJobSearcher(search, AsyncMock(), MagicMock(), settings)
    await searcher._search_keyword("Java Developer", "Remote")
    query = parse_qs(urlparse(search.navigate_to_search.call_args.args[0]).query)
    assert query["location"] == ["India"]
    assert query["f_WT"] == ["2"]


@pytest.mark.asyncio
async def test_modern_description_excludes_navigation_and_recommended_jobs(search_page):
    from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage

    search, page = search_page
    await page.set_content(
        """<div><nav>Navigation</nav><h1>Java Developer</h1>
    <div componentkey="JobDetails_AboutTheJob_101">About the job: Java and Spring Boot. 5+ years of experience required.</div>
    <div componentkey="JobDetailsSimilarJobsSlot_101">Unrelated Python roles. """
        + "recommended job " * 100
        + "</div></div>"
    )
    sidebar = await search.extract_sidebar_details()
    details = await LinkedInJobDetailPage(search._engine, AsyncMock()).extract_job_details()
    for result in [sidebar, details]:
        assert "5+ years of experience" in result["description"]
        assert "recommended job" not in result["description"]
