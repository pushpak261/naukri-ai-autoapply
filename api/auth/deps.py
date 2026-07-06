"""
FastAPI dependency injection helpers for JWT-based authentication.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth.jwt import verify_access_token
from api.deps import state

_bearer = HTTPBearer(auto_error=False)


def _resolve_secret() -> str:
    if state.settings and state.settings.jwt_secret:
        return state.settings.jwt_secret
    secret_file = state.settings.data_dir / ".jwt_secret" if state.settings else None
    if secret_file and secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    if secret_file:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secret, encoding="utf-8")
    return secret


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """
    FastAPI dependency that extracts and verifies the JWT access token
    from the Authorization header.

    Returns the authenticated user's email string.

    Raises HTTP 401 if the token is missing, expired, or invalid.
    """
    secret = _resolve_secret()

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_access_token(credentials.credentials, secret)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email: str = payload.get("sub", "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    return email


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str | None:
    """
    Like get_current_user but returns None instead of raising on missing/invalid token.
    Used for routes that work both authenticated and unauthenticated.
    """
    secret = _resolve_secret()
    if credentials is None:
        return None

    payload = verify_access_token(credentials.credentials, secret)
    if payload is None:
        return None
    return payload.get("sub")
