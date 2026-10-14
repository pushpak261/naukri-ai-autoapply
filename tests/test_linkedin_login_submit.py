"""Never report a login attempt when the sign-in button was not clicked."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.linked_agent.browser.pages.login import LinkedInLoginPage
from src.linked_agent.config.constants import LoginSelectors


@pytest.mark.asyncio
async def test_missing_sign_in_button_is_reported():
    engine = Mock()
    interactions = Mock()
    interactions.safe_click = AsyncMock(return_value=False)
    login = LinkedInLoginPage(engine, interactions)
    login._find_input_by_js = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="Could not click"):
        await login.submit_login()


@pytest.mark.asyncio
async def test_localized_button_is_used_before_english_selector():
    engine = Mock()
    engine.page.evaluate = AsyncMock(return_value='[data-agent-login-submit="true"]')
    interactions = Mock()
    interactions.safe_click = AsyncMock(return_value=True)
    login = LinkedInLoginPage(engine, interactions)
    login._find_input_by_js = AsyncMock(return_value="#password")
    with patch("src.linked_agent.browser.pages.login.asyncio.sleep", new=AsyncMock()):
        await login.submit_login()
    interactions.safe_click.assert_awaited_once_with('[data-agent-login-submit="true"]', force=True)


@pytest.mark.asyncio
async def test_legacy_button_selector_remains_supported():
    engine = Mock()
    interactions = Mock()
    interactions.safe_click = AsyncMock(return_value=True)
    login = LinkedInLoginPage(engine, interactions)
    login._find_input_by_js = AsyncMock(return_value=None)
    with patch("src.linked_agent.browser.pages.login.asyncio.sleep", new=AsyncMock()):
        await login.submit_login()
    interactions.safe_click.assert_awaited_once_with(LoginSelectors.LOGIN_BUTTON, force=True)
