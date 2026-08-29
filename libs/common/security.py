"""
Shared secret-encryption helpers.

Used to avoid storing sensitive values (e.g. Naukri account passwords) in
plaintext in ``config.yaml``. Values are stored as ``enc:<fernet-token>`` and
decrypted transparently by the settings loader.

The key is taken from ``SESSION_ENCRYPTION_KEY`` (required in production). When
unset (local dev) it is derived deterministically from the project root so the
system still works without manual setup — this is convenience, not real secrecy,
so production deployments MUST set ``SESSION_ENCRYPTION_KEY``.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet

ENC_PREFIX = "enc:"


def _project_root() -> Path:
    # libs/common/security.py -> ../../.. : common/ then libs/ then project root.
    return Path(__file__).resolve().parent.parent.parent


def _derive_key(raw: str) -> bytes:
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def resolve_encryption_key() -> bytes:
    env = os.environ.get("SESSION_ENCRYPTION_KEY")
    if env:
        return _derive_key(env)
    # Deterministic fallback for local dev only (NOT secure — set the env var in prod).
    return _derive_key(f"local-{_project_root()}")


def encrypt_value(plain: str) -> str:
    """Encrypt a string, returning ``enc:<token>``."""
    if not plain:
        return plain
    fernet = Fernet(resolve_encryption_key())
    token = fernet.encrypt(plain.encode("utf-8")).decode("utf-8")
    return ENC_PREFIX + token


def decrypt_value(maybe: str) -> str:
    """Decrypt an ``enc:<token>`` value; return other strings unchanged."""
    if not maybe or not maybe.startswith(ENC_PREFIX):
        return maybe
    try:
        fernet = Fernet(resolve_encryption_key())
        return fernet.decrypt(maybe[len(ENC_PREFIX) :].encode("utf-8")).decode("utf-8")
    except Exception:
        # If we cannot decrypt (key rotated / corrupted), fail safe to empty.
        return ""
