"""Dashboard session status must read the encrypted state written by both agents."""

import json
from types import SimpleNamespace

import pytest
import yaml
from cryptography.fernet import Fernet

from api.deps import AppState, current_state
from api.routes import data, sessions
from api.tenants import CODE_ROOT, agent_environment, load_user_settings
from src.linked_agent.browser.engine import LinkedInPlaywrightEngine
from src.naukri_agent.browser.engine import PlaywrightEngine


@pytest.mark.parametrize("routes", [data, sessions])
@pytest.mark.parametrize("engine", [PlaywrightEngine, LinkedInPlaywrightEngine])
@pytest.mark.parametrize("key", ["deployment-passphrase", Fernet.generate_key().decode(), ""])
def test_status_reads_browser_encryption(routes, engine, key, tmp_path):
    settings = SimpleNamespace(project_root=tmp_path, session_encryption_key=key)
    payload = b'{"cookies":[]}'
    encrypted = engine._init_fernet(settings).encrypt(payload)
    assert encrypted != payload
    assert routes._try_decrypt_session(encrypted, settings) == payload


@pytest.mark.parametrize("routes", [data, sessions])
def test_wrong_key_does_not_decrypt_or_change_existing_state(routes, tmp_path):
    settings = SimpleNamespace(project_root=tmp_path, session_encryption_key="wrong-key")
    encrypted = Fernet(Fernet.generate_key()).encrypt(b'{"cookies":[]}')
    assert routes._try_decrypt_session(encrypted, settings) == encrypted
    assert routes._try_decrypt_session(b'{"cookies":[]}', settings) == b'{"cookies":[]}'


@pytest.mark.parametrize("host_key", ["saved-host-passphrase", None])
def test_tenant_status_and_agent_share_host_key(tmp_path, monkeypatch, host_key):
    if host_key is None:
        monkeypatch.delenv("SESSION_ENCRYPTION_KEY", raising=False)
    else:
        monkeypatch.setenv("SESSION_ENCRYPTION_KEY", host_key)
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
    runtime = AppState()
    runtime.user_id = "test-tenant"
    runtime.settings = load_user_settings(tmp_path)
    token = current_state.set(runtime)
    try:
        expected = host_key or f"local-{CODE_ROOT}"
        assert runtime.settings.session_encryption_key == expected
        assert agent_environment()["SESSION_ENCRYPTION_KEY"] == expected
    finally:
        current_state.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("routes", [data, sessions])
async def test_encrypted_saved_sessions_are_visible_after_dashboard_restart(
    routes, tmp_path, monkeypatch
):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", "host-session-passphrase")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "linkedin_config.yaml").write_text(
        yaml.safe_dump({"linkedin": {"email": "candidate@example.invalid"}}), encoding="utf-8"
    )
    runtime = AppState()
    runtime.user_id = "test-tenant"
    runtime.active_account_email = "candidate@example.invalid"
    runtime.settings = load_user_settings(tmp_path)
    for platform, directory, engine in [
        ("naukri", tmp_path / "data/sessions", PlaywrightEngine),
        ("linkedin", tmp_path / "data/linkedin/sessions", LinkedInPlaywrightEngine),
    ]:
        directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"cookies": [{"domain": f".{platform}.com", "name": "session", "value": "fixture"}]}
        ).encode()
        session_path = directory / f"{platform}_session_candidate_at_example_dot_invalid.json"
        session_path.write_bytes(engine._init_fernet(runtime.settings).encrypt(payload))
    token = current_state.set(runtime)
    try:
        for platform in ("naukri", "linkedin"):
            status = await routes.session_status(platform=platform, account="")
            assert status["valid"] is True
            assert status["cookie_count"] == 1
            assert status["message"] == "Naukri: Active | LinkedIn: Active"
    finally:
        current_state.reset(token)
