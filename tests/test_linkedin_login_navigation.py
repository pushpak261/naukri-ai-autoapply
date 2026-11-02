"""Login readiness depends on the form, not unrelated third-party scripts."""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from playwright.async_api import TimeoutError

from src.linked_agent.browser.pages.login import LinkedInLoginPage


@pytest.mark.asyncio
async def test_navigation_waits_for_password_field_without_network_idle():
    engine = Mock()
    engine.page.goto = AsyncMock()
    field = engine.page.locator.return_value.first
    field.wait_for = AsyncMock()
    interactions = Mock()
    interactions.wait_for_navigation_complete = AsyncMock()
    with patch("src.linked_agent.browser.pages.login.asyncio.sleep", new=AsyncMock()):
        await LinkedInLoginPage(engine, interactions).navigate()
    field.wait_for.assert_awaited_once_with(state="visible", timeout=30_000)
    interactions.wait_for_navigation_complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticated_surface_is_accepted_when_the_form_never_renders():
    engine = Mock()
    engine.page.goto = AsyncMock()
    engine.page.locator.return_value.first.wait_for = AsyncMock(
        side_effect=TimeoutError("No login form")
    )
    engine.page.wait_for_function = AsyncMock(return_value=True)
    with patch("src.linked_agent.browser.pages.login.asyncio.sleep", new=AsyncMock()):
        await LinkedInLoginPage(engine, Mock()).navigate()
    engine.page.wait_for_function.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_form_does_not_silently_continue_to_credentials():
    engine = Mock()
    engine.page.goto = AsyncMock()
    engine.page.locator.return_value.first.wait_for = AsyncMock(side_effect=TimeoutError("No login form"))
    engine.page.wait_for_function = AsyncMock(side_effect=TimeoutError("No auth surface"))
    with pytest.raises(TimeoutError, match="No login form"), patch(
        "src.linked_agent.browser.pages.login.asyncio.sleep", new=AsyncMock()
    ):
        await LinkedInLoginPage(engine, Mock()).navigate()


@pytest.mark.asyncio
async def test_logged_in_indicator_wins_over_a_visible_login_link():
    from src.linked_agent.config.constants import LoginSelectors

    avatar = Mock()
    avatar.is_visible = AsyncMock(return_value=True)
    login_link = Mock()
    login_link.is_visible = AsyncMock(return_value=True)
    page = Mock()

    async def query(selector):
        if selector == LoginSelectors.LOGGED_IN_INDICATORS[0]:
            return avatar
        if selector == LoginSelectors.NOT_LOGGED_IN_INDICATORS:
            return login_link
        return None

    page.query_selector = AsyncMock(side_effect=query)
    engine = Mock()
    engine.page = page

    assert await LinkedInLoginPage(engine, Mock()).is_logged_in() is True
