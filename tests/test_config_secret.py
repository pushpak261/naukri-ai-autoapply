import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEAK = "Lightning@6!"


def _config_text() -> str | None:
    p = ROOT / "config.yaml"
    return p.read_text(encoding="utf-8") if p.exists() else None


def test_config_has_no_plaintext_password():
    text = _config_text()
    if text is None:
        pytest.skip("config.yaml not present in this environment")
    assert LEAK not in text


def test_config_password_is_encrypted():
    p = ROOT / "config.yaml"
    if not p.exists():
        pytest.skip("config.yaml not present in this environment")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    pw = (data.get("naukri") or {}).get("password", "")
    assert pw.startswith("enc:") or pw == "", "naukri password must be encrypted at rest"
