"""Tests for canonical resume path resolution."""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock

from src.naukri_agent.utils.helpers import (
    CANONICAL_RESUME_NAME,
    patch_settings_resume_path,
    resolve_resume_path,
)


def test_resolve_prefers_newer_repo_root_resume(tmp_path):
    backend_root = tmp_path / "backend"
    resumes_dir = backend_root / "data" / "resumes"
    resumes_dir.mkdir(parents=True)

    repo_resume = tmp_path / "data" / "resumes" / CANONICAL_RESUME_NAME
    repo_resume.parent.mkdir(parents=True)
    repo_resume.write_bytes(b"newer resume bytes")

    canonical = resumes_dir / CANONICAL_RESUME_NAME
    canonical.write_bytes(b"older resume bytes")
    time.sleep(0.01)
    os.utime(repo_resume, None)

    settings = MagicMock()
    settings.project_root = backend_root
    settings.resumes_dir = resumes_dir
    settings.resume.path = "data/resumes/resume_old.pdf"
    settings.ensure_dirs = MagicMock()

    resolved = resolve_resume_path(settings)

    assert resolved == canonical.resolve()
    assert canonical.read_bytes() == b"newer resume bytes"


def test_patch_settings_resume_path_updates_config(tmp_path):
    backend_root = tmp_path / "backend"
    resumes_dir = backend_root / "data" / "resumes"
    resumes_dir.mkdir(parents=True)

    resume = resumes_dir / CANONICAL_RESUME_NAME
    resume.write_bytes(b"resume content")

    settings = MagicMock()
    settings.project_root = backend_root
    settings.resumes_dir = resumes_dir
    settings.resume.path = "data/resumes/resume_old.pdf"
    settings.ensure_dirs = MagicMock()

    path = patch_settings_resume_path(settings)

    assert path == resume.resolve()
    assert settings.resume.path == "data/resumes/resume.pdf"
