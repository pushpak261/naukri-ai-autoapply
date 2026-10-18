"""The client bundle must not inherit the developer's live account artifacts."""
from zipfile import ZipFile

import pytest

from scripts import export_client


@pytest.mark.parametrize("name", [
    "config.yaml", "linkedin_config.yaml", "resume.pdf", "session.enc",
    ".env", "frontend/.env.local", "data/users/account/config.yaml",
    "local-workspace/.session_key", "frontend/node_modules/package/index.js",
    "frontend/dist/index.html", "debug_artifacts/screenshot.png",
    "../secrets.py", "/etc/passwd",
])
def test_export_rejects_private_or_generated_files(name):
    assert not export_client.include_file(name)


def test_export_preserves_data_service_source():
    assert export_client.include_file("services/data/main.py")


def test_export_uses_clean_settings_without_modifying_working_config(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "frontend/src").mkdir(parents=True)
    (root / "frontend/src/App.tsx").write_text("export default function App() {}")
    (root / "frontend/tests").mkdir(parents=True)
    (root / "frontend/tests/api.test.mjs").write_text("// regression suite")
    (root / "tests").mkdir()
    (root / "tests/test_new_regression.py").write_text("def test_new(): pass")
    (root / "config.yaml").write_text("password: PRIVATE\ndry_run: false")
    (root / "resume.pdf").write_bytes(b"personal resume")
    (root / "session.enc").write_bytes(b"private session")
    monkeypatch.setattr(export_client, "ROOT", root)
    monkeypatch.setattr(export_client.subprocess, "check_output", lambda *a, **k:
                        b"config.yaml\0resume.pdf\0session.enc\0frontend/src/App.tsx\0")
    output = tmp_path / "client.zip"
    export_client.export_bundle(output)
    with ZipFile(output) as bundle:
        assert "resume.pdf" not in bundle.namelist()
        assert "session.enc" not in bundle.namelist()
        assert b"PRIVATE" not in bundle.read("config.yaml")
        assert b"dry_run: true" in bundle.read("config.yaml")
        assert b"${NAUKRI_PASSWORD:-}" in bundle.read("config.yaml")
        assert b"${LINKEDIN_PASSWORD:-}" in bundle.read("linkedin_config.yaml")
        assert "frontend/src/App.tsx" in bundle.namelist()
        assert "frontend/tests/api.test.mjs" in bundle.namelist()
        assert "tests/test_new_regression.py" in bundle.namelist()
        assert "RELEASE_MANIFEST.txt" in bundle.namelist()
    assert "PRIVATE" in (root / "config.yaml").read_text()
