import time

import jwt as pyjwt
import pytest

from libs.common.auth import resolve_jwt_secret, verify_access_token

SECRET = "unit-test-secret"


def _make(typ: str = "access", exp: int | None = None) -> str:
    payload = {"sub": "user@example.com", "iat": 0, "type": typ}
    if exp is not None:
        payload["exp"] = exp
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def test_valid_token():
    assert verify_access_token(_make(), SECRET)["sub"] == "user@example.com"


def test_wrong_secret_rejected():
    assert verify_access_token(_make(), "other-secret") is None


def test_wrong_type_rejected():
    assert verify_access_token(_make(typ="refresh"), SECRET) is None


def test_expired_token_rejected():
    assert verify_access_token(_make(exp=-10), SECRET) is None


def test_resolve_fallback_returns_none_without_file(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    import pathlib

    monkeypatch.setattr("libs.common.auth._project_root", lambda: pathlib.Path("/nonexistent-dir-xyz"))
    assert resolve_jwt_secret() is None


def test_resolve_uses_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "env-secret")
    assert resolve_jwt_secret() == "env-secret"
