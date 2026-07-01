"""
Fernet encryption helpers for resume, profile, and session files.

Used by CLI init, local setup scripts, and GitHub Actions decrypt steps.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ENCRYPTED_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("resume.pdf.enc", "resume.pdf"),
    ("resume_profile.json.enc", "resume_profile.json"),
    ("session.enc", "data/sessions/naukri_session.json"),
)


def load_fernet_key(project_root: Path | None = None) -> bytes | None:
    """Load the Fernet key from ``resume_key.txt`` or the ``RESUME_KEY`` env var."""
    root = project_root or Path.cwd()

    key_file = root / "resume_key.txt"
    if key_file.exists():
        return key_file.read_bytes().strip()

    env_key = os.environ.get("RESUME_KEY", "").strip()
    if env_key:
        return env_key.encode()

    return None


def get_cipher(project_root: Path | None = None) -> Fernet | None:
    """Return a Fernet cipher when a key is available."""
    key = load_fernet_key(project_root)
    if not key:
        return None
    return Fernet(key)


def encrypt_file(source: Path, destination: Path, cipher: Fernet) -> None:
    """Encrypt *source* into *destination*."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(cipher.encrypt(source.read_bytes()))


def decrypt_file(source: Path, destination: Path, cipher: Fernet) -> None:
    """Decrypt *source* into *destination*."""
    try:
        plaintext = cipher.decrypt(source.read_bytes())
    except InvalidToken as exc:
        raise ValueError(
            f"Could not decrypt {source.name} — the key in resume_key.txt / "
            "RESUME_KEY does not match the encrypted file."
        ) from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(plaintext)


def decrypt_local_secrets(project_root: Path, *, force: bool = False) -> list[str]:
    """
    Decrypt encrypted artifacts into their plaintext paths when possible.

    Returns a list of human-readable status messages (success or skip).
    """
    messages: list[str] = []
    cipher = get_cipher(project_root)
    if cipher is None:
        messages.append(
            "No decryption key found (resume_key.txt or RESUME_KEY env var). "
            "Place resume.pdf in the backend directory, or add your key and re-run init."
        )
        return messages

    for enc_name, plain_name in ENCRYPTED_ARTIFACTS:
        enc_path = project_root / enc_name
        plain_path = project_root / plain_name

        if not enc_path.exists():
            continue
        if plain_path.exists() and not force:
            messages.append(f"Skipped {plain_name} (already exists).")
            continue

        try:
            decrypt_file(enc_path, plain_path, cipher)
        except ValueError as exc:
            messages.append(str(exc))
            continue

        messages.append(f"Decrypted {enc_name} → {plain_name}")

    return messages


def generate_and_save_key(project_root: Path) -> bytes:
    """Generate a new Fernet key and write it to ``resume_key.txt``."""
    key = Fernet.generate_key()
    key_file = project_root / "resume_key.txt"
    key_file.write_bytes(key)
    return key
