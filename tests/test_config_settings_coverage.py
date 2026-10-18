"""Structural tests for the agent settings models."""

from src.linked_agent.config.settings import Settings as LinkedInSettings
from src.naukri_agent.config.settings import Settings as NaukriSettings


def test_naukri_settings_structure():
    """Naukri settings expose the sections the agent relies on."""
    settings = NaukriSettings()

    assert settings is not None
    assert settings.naukri is not None
    assert settings.application is not None
    assert settings.resume is not None
    assert settings.search is not None
    assert settings.logging is not None


def test_linkedin_settings_structure():
    """LinkedIn settings expose the sections the agent relies on."""
    settings = LinkedInSettings()

    assert settings is not None
    assert settings.linkedin is not None
    assert settings.application is not None
    assert settings.resume is not None
    assert settings.search is not None
    assert settings.logging is not None


def test_naukri_settings_paths_are_derived_from_project_root(tmp_path):
    """Resume/session/data directories hang off the configured project root."""
    settings = NaukriSettings(project_root=tmp_path)
    settings.ensure_dirs()

    assert settings.resumes_dir.is_dir()
    assert settings.project_root in settings.resumes_dir.parents
    assert settings.project_root in settings.data_dir.parents
    assert settings.project_root in settings.sessions_dir.parents


def test_linkedin_paths_use_custom_workspace_and_preserve_explicit_paths(tmp_path):
    settings = LinkedInSettings(project_root=tmp_path)
    assert settings.data_dir == tmp_path / "data" / "linkedin"
    assert settings.sessions_dir == settings.data_dir / "sessions"
    assert settings.resumes_dir == tmp_path / "data" / "resumes"
    custom = tmp_path / "custom.db"
    assert LinkedInSettings(project_root=tmp_path, db_path=custom).db_path == custom
