"""Untrusted resume content must never choose a profile write destination."""

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from api.deps import state
from api.routes import resume
from tests.test_dashboard_features import dashboard  # noqa: F401

# Imported fixture names are intentionally shadowed by test parameters.
# ruff: noqa: F811


def test_profile_write_replaces_link_without_modifying_its_target(tmp_path, monkeypatch):
    target = tmp_path / "other-account.json"
    target.write_bytes(b"other account must remain unchanged")
    profile_path = tmp_path / "resume_profile.json"
    os.link(target, profile_path)
    monkeypatch.setattr(resume, "_get_profile_json_path", lambda: profile_path)
    contents = b'{"uploaded_file_path":"../../other-account.json","name":"Candidate"}'

    resume._write_profile_contents(contents)

    assert profile_path.read_bytes() == contents
    assert target.read_bytes() == b"other account must remain unchanged"
    assert not list(tmp_path.glob(".resume_profile_*"))


def test_failed_profile_replacement_preserves_previous_file(tmp_path, monkeypatch):
    profile_path = tmp_path / "resume_profile.json"
    profile_path.write_bytes(b"previous profile")
    monkeypatch.setattr(resume, "_get_profile_json_path", lambda: profile_path)

    def fail_replace(self, target):
        raise OSError("replacement failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        resume._write_profile_contents(b"new profile")

    assert profile_path.read_bytes() == b"previous profile"
    assert not list(tmp_path.glob(".resume_profile_*"))


@pytest.mark.asyncio
async def test_cached_upload_ignores_paths_in_filename_and_profile(dashboard):
    content = b"cached resume fixture"
    outside = state.settings.project_root / "other-account.json"
    outside.write_text("keep this file", encoding="utf-8")
    reviewed = {
        "name": "Reviewed Candidate",
        "file_hash": hashlib.sha256(content).hexdigest(),
        "uploaded_file_path": str(outside),
        "summary": "../../other-account.json",
    }
    profile_path = state.settings.project_root / "resume_profile.json"
    profile_path.write_text(json.dumps(reviewed), encoding="utf-8")
    response = await dashboard.post(
        "/api/resume/upload?mode=local",
        files={"file": ("../../other-account.pdf", content, "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cached"
    saved = json.loads(profile_path.read_text(encoding="utf-8"))
    destination = Path(saved["uploaded_file_path"])
    assert destination.parent == state.settings.resumes_dir
    assert destination.read_bytes() == content
    assert saved["summary"] == reviewed["summary"]
    assert outside.read_text(encoding="utf-8") == "keep this file"
    assert not list(profile_path.parent.glob(".resume_profile_*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_profile", [False, True])
async def test_ai_upload_failure_restores_exact_previous_profile(
    dashboard, monkeypatch, existing_profile
):
    state.settings.ai.gemini_api_key = "test-only-api-key"
    profile_path = state.settings.project_root / "resume_profile.json"
    previous = '{"name":"Renée","summary":"../../private.json"}\n'.encode()
    if existing_profile:
        profile_path.write_bytes(previous)

    async def fail_after_partial_save(*args, **kwargs):
        profile_path.write_bytes(b"partial result")
        raise ValueError("provider failure")

    monkeypatch.setattr(resume.ResumeParser, "parse", AsyncMock(side_effect=fail_after_partial_save))
    response = await dashboard.post(
        "/api/resume/upload?mode=ai",
        files={"file": ("../../private.pdf", b"new resume fixture", "application/pdf")},
    )

    assert response.status_code == 503, response.text
    if existing_profile:
        assert profile_path.read_bytes() == previous
    else:
        assert not profile_path.exists()
    assert not list(state.settings.resumes_dir.iterdir())
    assert not list(profile_path.parent.glob(".resume_profile_*"))
