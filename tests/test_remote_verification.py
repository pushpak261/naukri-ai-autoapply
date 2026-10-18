import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, UploadFile
from io import BytesIO
from cryptography.fernet import Fernet

from api import remote_verification as remote
from src.linked_agent.browser.engine import LinkedInPlaywrightEngine
from src.linked_agent.config.settings import Settings


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "https://localhost/", "https://linkedin.com.evil.test/", "file:///etc/passwd", "https://169.254.169.254/"])
def test_private_and_unrelated_browser_requests_are_blocked(url):
    assert not remote.allowed_url(url)


@pytest.mark.parametrize("url", ["https://www.linkedin.com/login", "https://www.google.com/recaptcha/", "https://www.gstatic.com/recaptcha/"])
def test_required_verification_services_are_allowed(url):
    assert remote.allowed_url(url)


def test_browser_owner_cannot_be_impersonated():
    controller = remote.BrowserController()
    controller.owner = "owner@example.com"
    with pytest.raises(HTTPException) as error:
        controller.check_owner("other@example.com")
    assert error.value.status_code == 404


def test_passphrase_session_key_does_not_fall_back_to_plaintext():
    engine = LinkedInPlaywrightEngine(Settings(session_encryption_key="a-private-host-passphrase"))
    encrypted = engine._encrypt(b"sensitive cookie")
    assert b"sensitive cookie" not in encrypted
    assert engine._fernet.decrypt(encrypted) == b"sensitive cookie"


@pytest.mark.asyncio
async def test_agent_capacity_is_reserved_by_verification(monkeypatch):
    from api.agent_runtime import ensure_browser_capacity
    controller = remote.BrowserController()
    controller.phase = "starting"
    monkeypatch.setattr(remote, "controller", controller)
    with pytest.raises(HTTPException) as error:
        ensure_browser_capacity()
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_cancel_does_not_save_unauthenticated_browser(monkeypatch):
    controller = remote.BrowserController()
    controller.engine = Mock()
    controller.engine.close = AsyncMock()
    controller.engine.save_session = AsyncMock()
    engine = controller.engine
    await controller.close()
    engine.save_session.assert_not_awaited()
    engine.close.assert_awaited_once()
    assert not controller.active()


@pytest.mark.asyncio
async def test_unverified_login_is_never_saved(monkeypatch):
    controller = remote.BrowserController()
    controller.owner = "owner@example.com"
    controller.phase = "ready"
    controller.engine = Mock()
    controller.engine.page.url = "https://www.linkedin.com/checkpoint/"
    controller.engine._context.cookies = AsyncMock(return_value=[])
    controller.engine.save_session = AsyncMock()
    page = Mock()
    page.verify_auth_state = AsyncMock(return_value=(False, "checkpoint"))
    monkeypatch.setattr(remote, "LinkedInLoginPage", lambda *args: page)
    monkeypatch.setattr(remote, "controller", controller)
    with pytest.raises(HTTPException) as error:
        await remote.finish(controller.owner)
    assert error.value.status_code == 422
    controller.engine.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_verification_resource_cannot_be_saved_as_linkedin_login(monkeypatch):
    controller = remote.BrowserController()
    controller.owner = "owner@example.com"
    controller.phase = "ready"
    controller.engine = Mock()
    controller.engine.page.url = "https://www.google.com/"
    controller.engine.save_session = AsyncMock()
    monkeypatch.setattr(remote, "controller", controller)
    with pytest.raises(HTTPException) as error:
        await remote.finish(controller.owner)
    assert error.value.status_code == 422
    controller.engine.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_encrypted_backup_roundtrip_and_owner_binding(tmp_path, monkeypatch):
    settings = Settings(project_root=tmp_path, sessions_dir=tmp_path / "sessions", session_encryption_key=Fernet.generate_key().decode(), linkedin={"email": "linkedin@example.com"})
    monkeypatch.setattr(remote, "settings_for_current_user", lambda: settings)
    engine = LinkedInPlaywrightEngine(settings)
    engine._session_path.parent.mkdir(parents=True)
    state = {"cookies": [{"name": "li_at", "value": "fake-session", "domain": ".linkedin.com", "path": "/"}], "origins": []}
    engine._session_path.write_bytes(engine._encrypt(json.dumps(state).encode()))
    response = await remote.backup("owner@example.com")
    assert b"fake-session" not in response.body
    await remote.restore(UploadFile(file=BytesIO(response.body)), "owner@example.com")
    with pytest.raises(HTTPException):
        await remote.restore(UploadFile(file=BytesIO(response.body)), "other@example.com")
    with pytest.raises(HTTPException):
        await remote.restore(UploadFile(file=BytesIO(json.dumps(state).encode())), "owner@example.com")


def test_naukri_passphrase_sessions_are_encrypted_and_legacy_json_is_readable():
    from src.naukri_agent.browser.engine import PlaywrightEngine
    from src.naukri_agent.config.settings import Settings as NaukriSettings
    engine = PlaywrightEngine(NaukriSettings(session_encryption_key="host-passphrase"))
    payload = b'{"cookies": [], "origins": []}'
    encrypted = engine._encrypt(payload)
    assert encrypted != payload
    assert engine._decrypt(encrypted) == payload
    assert engine._decrypt(payload) == payload
    other = PlaywrightEngine(NaukriSettings(session_encryption_key="host-passphrase"))
    assert other._decrypt(encrypted) == payload
