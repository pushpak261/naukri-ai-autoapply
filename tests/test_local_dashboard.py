from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi import Response

from api.local import LocalDashboard
from api.routes.auth import _set_refresh_cookie
from scripts.local_dashboard import prepare_workspace
from src.linked_agent.browser.login import LinkedInLoginHandler


def test_local_workspace_preserves_settings_and_encryption_key(tmp_path):
    key = prepare_workspace(tmp_path)
    (tmp_path / "config.yaml").write_text("existing user settings")
    assert prepare_workspace(tmp_path) == key
    assert (tmp_path / "config.yaml").read_text() == "existing user settings"
    from cryptography.fernet import Fernet
    assert Fernet(key.encode()).decrypt(Fernet(key.encode()).encrypt(b"session")) == b"session"


def test_refresh_cookie_only_allows_http_in_explicit_local_mode(monkeypatch):
    monkeypatch.delenv("LOCAL_AGENT_MODE", raising=False)
    response = Response()
    _set_refresh_cookie(response, "test")
    assert "Secure" in response.headers["set-cookie"]
    monkeypatch.setenv("LOCAL_AGENT_MODE", "1")
    response = Response()
    _set_refresh_cookie(response, "test")
    assert "Secure" not in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_dashboard_routes_do_not_swallow_api_or_missing_assets(tmp_path):
    (tmp_path / "index.html").write_text("local dashboard")
    from fastapi import FastAPI
    api = FastAPI()
    app = LocalDashboard(api, tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        assert (await client.get("/")).text == "local dashboard"
        assert (await client.get("/agent-control")).text == "local dashboard"
        assert (await client.get("/api/missing")).status_code == 404
        assert (await client.get("/assets/missing.js")).status_code == 404
        assert (await client.get("/config.yaml")).status_code == 404


@pytest.mark.asyncio
async def test_manual_verification_saves_only_verified_session():
    page = Mock()
    page.is_logged_in = AsyncMock(side_effect=[False, True])
    page.verify_auth_state = AsyncMock(return_value=(True, ""))
    engine = Mock()
    engine.save_session = AsyncMock()
    handler = LinkedInLoginHandler(page, engine, strategy=Mock())
    with patch("src.linked_agent.browser.login.asyncio.sleep", new=AsyncMock()):
        assert await handler._wait_for_manual_login()
    engine.mark_session_authenticated.assert_called_once()
    engine.save_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_timeout_never_saves_unauthenticated_session():
    page = Mock()
    page.is_logged_in = AsyncMock(return_value=False)
    engine = Mock()
    engine.save_session = AsyncMock()
    handler = LinkedInLoginHandler(page, engine, strategy=Mock())
    with patch("src.linked_agent.browser.login.asyncio.sleep", new=AsyncMock()):
        assert not await handler._wait_for_manual_login()
    engine.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_mode_never_submits_stored_password(monkeypatch):
    monkeypatch.setenv("LOCAL_AGENT_MODE", "1")
    page = Mock()
    page.navigate = AsyncMock()
    page.close_popups = AsyncMock()
    strategy = Mock()
    strategy.authenticate = AsyncMock()
    handler = LinkedInLoginHandler(page, Mock(), strategy=strategy, settings=Mock())
    handler._wait_for_manual_login = AsyncMock(return_value=True)
    with patch("src.linked_agent.browser.login.asyncio.sleep", new=AsyncMock()):
        assert await handler._perform_login()
    strategy.authenticate.assert_not_awaited()
