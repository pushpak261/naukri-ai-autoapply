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
    await page.set_content(
        """<div role="button" onclick="document.querySelector('[contenteditable]').style.display='block';document.querySelector('#semanticSearchBoxLocationList').style.display='block'">
    <div aria-label="Location Pune">Pune</div></div>
    <div contenteditable="true" aria-label="Location" style="display:none">Pune</div>
    <div id="semanticSearchBoxLocationList" style="display:none"><a href="#" onclick="event.preventDefault();const label=document.querySelector('[aria-label^=Location]');label.textContent='Mumbai Metropolitan Region';label.setAttribute('aria-label','Location Mumbai Metropolitan Region')">Mumbai Metropolitan Region</a></div>"""
    )
    await search._ensure_search_location("Mumbai")
    assert (
        await page.locator('[aria-label^="Location "]').inner_text() == "Mumbai Metropolitan Region"
    )
