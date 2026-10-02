import os
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _known_secrets() -> list[str]:
    """Real credentials, read from the environment rather than hardcoded.

    Hardcoding them here would re-introduce the very leak these tests guard
    against, since this file is tracked in git.
    """
    env_file = ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        except ImportError:
            pass

    return [
        value
        for name in ("NAUKRI_PASSWORD", "LINKEDIN_PASSWORD", "GMAIL_APP_PASSWORD", "GEMINI_API_KEY")
        if len(value := os.environ.get(name, "").strip()) >= 4
    ]


def _config_text() -> str | None:
    p = ROOT / "config.yaml"
    return p.read_text(encoding="utf-8") if p.exists() else None


def test_config_has_no_plaintext_password():
    text = _config_text()
    if text is None:
        pytest.skip("config.yaml not present in this environment")
    for secret in _known_secrets():
        assert secret not in text, f"config.yaml contains a plaintext secret from {secret[:2]}***"


def test_linkedin_config_has_no_plaintext_secrets():
    p = ROOT / "linkedin_config.yaml"
    if not p.exists():
        pytest.skip("linkedin_config.yaml not present in this environment")
    text = p.read_text(encoding="utf-8")
    for secret in _known_secrets():
        assert secret not in text, f"linkedin_config.yaml contains a plaintext secret from {secret[:2]}***"
    assert "password: ${LINKEDIN_PASSWORD" in text, (
        "linkedin_config.yaml must source the password from ${LINKEDIN_PASSWORD}, "
        "not store it inline"
    )


def test_config_password_is_encrypted():
    p = ROOT / "config.yaml"
    if not p.exists():
        pytest.skip("config.yaml not present in this environment")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    pw = (data.get("naukri") or {}).get("password", "")
    # Password can be encrypted (enc:) or use environment variable substitution
    is_encrypted = pw.startswith("enc:") or pw.startswith("${") or pw == ""
    assert is_encrypted, "naukri password must be encrypted or use env var substitution"
