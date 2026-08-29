"""
Shared authentication helpers for the gateway and services.

The gateway must verify the JWT that the frontend sends **locally** (no extra
network hop). Both the auth service and the gateway resolve the signing secret
the same way:

  1. ``JWT_SECRET`` environment variable (preferred, required in production).
  2. Otherwise the persisted ``data/.jwt_secret`` file (written by the auth
     service on first token issuance) so single-host / local-dev works.

This keeps the gateway and the auth service in agreement on the secret without
coupling them at runtime.
"""

from __future__ import annotations

import os
from pathlib import Path

import jwt as pyjwt

ALGORITHM = "HS256"
_JWT_SECRET_FILE = "data/.jwt_secret"


def _project_root() -> Path:
    # libs/common/auth.py -> ../../.. : common/ then libs/ then project root.
    return Path(__file__).resolve().parent.parent.parent


def resolve_jwt_secret() -> str | None:
    """Return the JWT signing secret, or ``None`` if none is configured."""
    env_secret = os.environ.get("JWT_SECRET")
    if env_secret:
        return env_secret

    secret_file = _project_root() / _JWT_SECRET_FILE
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    return None


def verify_access_token(token: str, secret: str | None = None) -> dict | None:
    """Verify an access token; return its payload or ``None`` if invalid."""
    secret = secret or resolve_jwt_secret()
    if not secret:
        return None
    try:
        payload = pyjwt.decode(token, secret, algorithms=[ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


def resolve_service_token() -> str | None:
    """
    Return the shared gateway<->service token (``SERVICE_TOKEN`` or
    ``DASHBOARD_API_KEY``). ``None`` means "auth not enforced" (dev mode).
    """
    return os.environ.get("SERVICE_TOKEN") or os.environ.get("DASHBOARD_API_KEY") or None
