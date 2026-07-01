"""Tests for login session detection and skip-login behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.naukri_agent.browser.login import LoginHandler, PasswordLoginStrategy
from src.naukri_agent.config.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        naukri={"email": "test@example.com", "password": "secret"},
    )


@pytest.fixture
def login_page() -> MagicMock:
    page = MagicMock()
    page.verify_active_session = AsyncMock(return_value=False)
    page.navigate_to_base = AsyncMock()
    page.wait_and_check_logged_in = AsyncMock(return_value=False)
    page.is_logged_in = AsyncMock(return_value=False)
    page.navigate = AsyncMock()
    page.close_popups = AsyncMock()
    page.get_login_error_text = AsyncMock(return_value="")
    return page


@pytest.fixture
def engine() -> MagicMock:
    eng = MagicMock()
    eng.save_session = AsyncMock()
    return eng


@pytest.mark.asyncio
async def test_login_skips_when_dashboard_session_active(
    login_page: MagicMock, engine: MagicMock, settings: Settings
) -> None:
    login_page.verify_active_session = AsyncMock(return_value=True)

    handler = LoginHandler(
        login_page=login_page,
        engine=engine,
        strategy=PasswordLoginStrategy(settings),
    )

    assert await handler.login() is True
    login_page.navigate.assert_not_called()
    engine.save_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_skips_before_login_form_when_dom_shows_logged_in(
    login_page: MagicMock, engine: MagicMock, settings: Settings
) -> None:
    login_page.verify_active_session = AsyncMock(side_effect=[False, True])
    login_page.wait_and_check_logged_in = AsyncMock(return_value=False)

    handler = LoginHandler(
        login_page=login_page,
        engine=engine,
        strategy=PasswordLoginStrategy(settings),
    )

    assert await handler.login() is True
    login_page.navigate.assert_not_called()
    assert engine.save_session.await_count >= 1


@pytest.mark.asyncio
async def test_perform_login_skips_when_already_logged_in_mid_flow(
    login_page: MagicMock, engine: MagicMock, settings: Settings
) -> None:
    login_page.verify_active_session = AsyncMock(return_value=True)

    handler = LoginHandler(
        login_page=login_page,
        engine=engine,
        strategy=PasswordLoginStrategy(settings),
    )

    assert await handler._perform_login() is True
    login_page.navigate.assert_not_called()


@pytest.mark.asyncio
async def test_login_runs_credentials_when_session_expired(
    login_page: MagicMock, engine: MagicMock, settings: Settings
) -> None:
    strategy = MagicMock()
    strategy.authenticate = AsyncMock(return_value=True)
    login_page.is_logged_in = AsyncMock(return_value=True)

    handler = LoginHandler(login_page=login_page, engine=engine, strategy=strategy)

    assert await handler.login() is True
    login_page.navigate.assert_awaited_once()
    strategy.authenticate.assert_awaited_once()
