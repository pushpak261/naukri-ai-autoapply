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


def test_naukri_settings_paths_are_derived_from_project_root():
    """Resume/session/data directories hang off the configured project root."""
    settings = NaukriSettings()

    assert settings.resumes_dir.is_dir()
    assert settings.project_root in settings.resumes_dir.parents
    assert settings.project_root in settings.data_dir.parents
    assert settings.project_root in settings.sessions_dir.parents