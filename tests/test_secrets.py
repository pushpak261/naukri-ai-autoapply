"""Tests for Fernet encryption helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.naukri_agent.utils.secrets import (
    decrypt_file,
    decrypt_local_secrets,
    encrypt_file,
    generate_and_save_key,
    load_fernet_key,
)


def test_generate_and_load_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    key = generate_and_save_key(tmp_path)
    assert (tmp_path / "resume_key.txt").exists()
    assert load_fernet_key(tmp_path) == key


def test_encrypt_decrypt_roundtrip(tmp_path: Path) -> None:
    cipher = Fernet(Fernet.generate_key())
    source = tmp_path / "resume.pdf"
    encrypted = tmp_path / "resume.pdf.enc"
    decrypted = tmp_path / "out.pdf"

    source.write_bytes(b"%PDF-1.4 test resume")
    encrypt_file(source, encrypted, cipher)
    decrypt_file(encrypted, decrypted, cipher)
    assert decrypted.read_bytes() == source.read_bytes()


def test_decrypt_local_secrets_skips_existing_plaintext(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key()
    (tmp_path / "resume_key.txt").write_bytes(key)
    cipher = Fernet(key)

    plain = tmp_path / "resume.pdf"
    enc = tmp_path / "resume.pdf.enc"
    plain.write_bytes(b"resume")
    encrypt_file(plain, enc, cipher)
    plain.unlink()

    # Plaintext recreated before decrypt runs
    plain.write_bytes(b"already here")

    monkeypatch.chdir(tmp_path)
    messages = decrypt_local_secrets(tmp_path)
    assert any("Skipped resume.pdf" in message for message in messages)
    assert plain.read_bytes() == b"already here"


def test_decrypt_local_secrets_without_key(tmp_path: Path) -> None:
    (tmp_path / "resume.pdf.enc").write_bytes(b"encrypted")
    messages = decrypt_local_secrets(tmp_path)
    assert len(messages) == 1
    assert "No decryption key found" in messages[0]
