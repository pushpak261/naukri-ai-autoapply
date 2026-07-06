"""
JWT token creation, verification, and encrypted disk persistence for
the dashboard authentication session.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt as pyjwt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

_TOKEN_FILE = "dashboard_session.enc"


def _derive_key(raw: str) -> bytes:
    """Derive a 32-byte Fernet-compatible key from an arbitrary secret string."""
    import hashlib

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:44].encode("utf-8")


def _get_fernet(settings: Any) -> Any:
    """Return a Fernet instance using the configured encryption key."""
    from cryptography.fernet import Fernet

    key = settings.jwt_encryption_key or secrets.token_hex(16)
    key_bytes = _derive_key(key)
    # Fernet keys must be 32 base64-encoded bytes — pad if needed
    import base64

    padded = base64.urlsafe_b64encode(key_bytes[:32].ljust(32, b"\0"))
    return Fernet(padded)


# ---------------------------------------------------------------------------
# Token creation / verification
# ---------------------------------------------------------------------------


def create_access_token(email: str, secret: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return pyjwt.encode(payload, secret, algorithm=ALGORITHM)


def create_refresh_token(email: str, secret: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "type": "refresh",
    }
    return pyjwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_access_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        payload = pyjwt.decode(token, secret, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


def verify_refresh_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        payload = pyjwt.decode(token, secret, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# Encrypted disk persistence for refresh token (survives server restart)
# ---------------------------------------------------------------------------


def save_refresh_token(settings: Any, token: str) -> None:
    f = _get_fernet(settings)
    encrypted = f.encrypt(token.encode("utf-8"))
    path = settings.data_dir / _TOKEN_FILE
    path.write_bytes(encrypted)


def load_refresh_token(settings: Any) -> str | None:
    path = settings.data_dir / _TOKEN_FILE
    if not path.exists():
        return None
    try:
        f = _get_fernet(settings)
        decrypted = f.decrypt(path.read_bytes())
        return decrypted.decode("utf-8")
    except Exception:
        return None


def delete_refresh_token(settings: Any) -> None:
    path = settings.data_dir / _TOKEN_FILE
    if path.exists():
        path.unlink()
