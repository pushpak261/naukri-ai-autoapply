"""First-time login should not navigate the homepage to restore absent state."""
from unittest.mock import AsyncMock, Mock

import pytest

from src.linked_agent.browser.login import LinkedInLoginHandler


@pytest.mark.asyncio
async def test_first_login_goes_directly_to_credentials():
    engine = Mock()
    engine.has_saved_session.return_value = False
    handler = LinkedInLoginHandler(Mock(), engine, strategy=Mock())
    handler._check_existing_session = AsyncMock(return_value=True)
    handler._perform_login = AsyncMock(return_value=True)
    assert await handler.login() is True
    handler._check_existing_session.assert_not_awaited()
    handler._perform_login.assert_awaited_once()
    engine.mark_session_authenticated.assert_not_called()


@pytest.mark.asyncio
async def test_saved_session_is_verified_before_skipping_credentials():
    engine = Mock()
    engine.has_saved_session.return_value = True
    handler = LinkedInLoginHandler(Mock(), engine, strategy=Mock())
    handler._check_existing_session = AsyncMock(return_value=True)
    handler._perform_login = AsyncMock(return_value=False)
    assert await handler.login() is True
    handler._check_existing_session.assert_awaited_once()
    handler._perform_login.assert_not_awaited()
    engine.mark_session_authenticated.assert_called_once()


@pytest.mark.asyncio
async def test_expired_saved_session_falls_back_to_credentials():
    engine = Mock()
    engine.has_saved_session.return_value = True
    handler = LinkedInLoginHandler(Mock(), engine, strategy=Mock())
    handler._check_existing_session = AsyncMock(return_value=False)
    handler._perform_login = AsyncMock(return_value=True)
    assert await handler.login() is True
    handler._check_existing_session.assert_awaited_once()
    handler._perform_login.assert_awaited_once()
