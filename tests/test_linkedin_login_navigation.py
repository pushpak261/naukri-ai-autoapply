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
    field.wait_for.assert_awaited_once_with(state="visible", timeout=90_000)
    interactions.wait_for_navigation_complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_form_does_not_silently_continue_to_credentials():
    engine = Mock()
    engine.page.goto = AsyncMock()
    engine.page.locator.return_value.first.wait_for = AsyncMock(side_effect=TimeoutError("No login form"))
    with pytest.raises(TimeoutError, match="No login form"):
        await LinkedInLoginPage(engine, Mock()).navigate()
