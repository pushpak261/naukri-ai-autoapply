"""
Pydantic settings model for the LinkedIn Agent.

Loads configuration from linkedin_config.yaml and merges with environment variable
overrides. Provides typed, validated access to all settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Project root (LinkedIn agent sits under src/linked_agent/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Nested config models
# ---------------------------------------------------------------------------
class LinkedInCredentials(BaseModel):
    """LinkedIn login credentials."""

    email: str = ""
    password: str = ""
    two_factor_code: str = ""  # For manual 2FA entry if needed
    gmail_otp_email: str = ""  # Gmail address for sending email notifications
    gmail_app_password: str = ""  # Gmail app password for SMTP


class AISettings(BaseModel):
    """Gemini AI configuration."""

    use_gemini: bool = False
    gemini_api_key: str = ""
    model: str = "gemini-2.5-flash"
    fallback_model: str | None = None
    enable_matching: bool = True
    abort_on_quota: bool = True
    temperature: float = 0.3
    max_output_tokens: int = 4096


class ResumeSettings(BaseModel):
    """Resume file settings."""

    path: str = ""


class SearchSettings(BaseModel):
    """Job search parameters."""

    keywords: list[str] = Field(default_factory=lambda: ["Software Engineer"])
    locations: list[str] = Field(default_factory=lambda: ["United States"])
    experience_level: list[str] = Field(default_factory=list)
    job_type: list[str] = Field(default_factory=list)
    work_type: str = ""  # on_site, remote, hybrid
    freshness: str = "past_week"
    max_pages: int = 3
    sort_by: str = "relevance"
    enable_heuristics: bool = True
    # Mandatory title filter: a job title MUST contain at least one of these
    # (word-boundary matched) for the agent to consider applying. Empty = no
    # mandatory requirement (any job from the search keywords is eligible).
    required_title_keywords: list[str] = Field(default_factory=list)

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        allowed = {"relevance", "date"}
        if v not in allowed:
            raise ValueError(f"sort_by must be one of {allowed}")
        return v

    @field_validator("freshness")
    @classmethod
    def validate_freshness(cls, v: str) -> str:
        allowed = {"any", "past_24h", "past_week", "past_month"}
        if v not in allowed:
            raise ValueError(f"freshness must be one of {allowed}")
        return v

    @field_validator("work_type")
    @classmethod
    def validate_work_type(cls, v: str) -> str:
        allowed = {"", "on_site", "remote", "hybrid"}
        if v not in allowed:
            raise ValueError(f"work_type must be one of {allowed}")
        return v


class ApplicationSettings(BaseModel):
    """Application behavior controls."""

    daily_cap: int = 50
    match_score_threshold: int = 70
    answer_questions_with_pdf: bool = True
    delay_between_applies_min: int = 60
    delay_between_applies_max: int = 180
    delay_between_actions_min: float = 3.0
    delay_between_actions_max: float = 8.0
    skip_external_apply: bool = False
    collect_external_jobs: bool = True
    email_recipient: str = ""
    dry_run: bool = False
    # LinkedIn-specific: always apply to Easy Apply jobs
    easy_apply_only: bool = False
    # Unfollow companies after applying (reduces noise)
    unfollow_after_apply: bool = True
    # Notification settings
    email_notifications_enabled: bool = False
    notify_on_apply: bool = True
    notify_on_failure: bool = True
    notify_on_scam: bool = True
    notify_on_match: bool = False
    # Retry settings
    max_retries: int = 3
    # Rate limiter settings (lower than Naukri — LinkedIn is stricter)
    rate_limit_capacity: float = 5.0
    rate_limit_refill_rate: float = 0.5


class ProfileSettings(BaseModel):
    """User profile details for auto-filling forms."""

    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    email: str = ""
    current_ctc: str = ""
    expected_ctc: str = ""
    notice_period: str = ""
    current_location: str = ""
    preferred_locations: list[str] = Field(default_factory=list)
    total_experience: str = ""


class ExclusionSettings(BaseModel):
    """Filters to skip certain jobs."""

    enable_scam_filter: bool = False
    fake_company_blocklist: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    description_keywords: list[str] = Field(default_factory=list)
    max_openings_without_logo: int = 30


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    log_to_file: bool = True
    log_dir: str = "data/logs"


# ---------------------------------------------------------------------------
# Root settings model
# ---------------------------------------------------------------------------
class Settings(BaseModel):
    """Complete LinkedIn agent settings loaded from linkedin_config.yaml + env vars."""

    linkedin: LinkedInCredentials = Field(default_factory=LinkedInCredentials)
    ai: AISettings = Field(default_factory=AISettings)
    resume: ResumeSettings = Field(default_factory=ResumeSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    exclusions: ExclusionSettings = Field(default_factory=ExclusionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # Dashboard API key for frontend authentication
    dashboard_api_key: str = ""
    # Session encryption key
    session_encryption_key: str = ""

    # Computed paths
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data" / "linkedin"
    sessions_dir: Path = PROJECT_ROOT / "data" / "linkedin" / "sessions"
    resumes_dir: Path = PROJECT_ROOT / "data" / "resumes"
    db_path: Path = PROJECT_ROOT / "data" / "linkedin" / "linkedin_agent.db"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def ensure_dirs(self) -> None:
        """Create required data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.resumes_dir.mkdir(parents=True, exist_ok=True)
        log_dir = self.project_root / self.logging.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)

    def validate_required(self) -> list[str]:
        """
        Check that the minimum configuration needed to run the agent is present.
        Returns a list of human-readable problem descriptions.
        """
        problems: list[str] = []

        if not self.linkedin.email:
            problems.append(
                "LinkedIn email is not set. Set LINKEDIN_EMAIL in your .env file "
                "or linkedin.email in linkedin_config.yaml."
            )
        if not self.linkedin.password:
            problems.append(
                "LinkedIn password is not set. Set LINKEDIN_PASSWORD in your .env "
                "or linkedin.password in linkedin_config.yaml."
            )
        if self.ai.use_gemini and not self.ai.gemini_api_key:
            problems.append(
                "Gemini API key is not set. Set GEMINI_API_KEY in your .env "
                "file or ai.gemini_api_key in linkedin_config.yaml."
            )

        resume_path = self.project_root / self.resume.path if self.resume.path else None
        if not resume_path:
            problems.append("Resume path is not configured (resume.path in linkedin_config.yaml).")
        elif not resume_path.exists():
            problems.append(f"Resume file not found at: {resume_path}")

        return problems


def _load_yaml_config() -> dict:
    """Load the linkedin_config.yaml file from the project root."""
    config_path = PROJECT_ROOT / "linkedin_config.yaml"
    if not config_path.exists():
        # Fallback: try config.yaml if linkedin-specific config doesn't exist
        config_path = PROJECT_ROOT / "config.yaml"
        if not config_path.exists():
            return {}
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _apply_env_overrides(config: dict) -> dict:
    """Override specific config values with environment variables."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)

    env_map = {
        ("linkedin", "email"): "LINKEDIN_EMAIL",
        ("linkedin", "password"): "LINKEDIN_PASSWORD",
        ("linkedin", "two_factor_code"): "LINKEDIN_2FA_CODE",
        ("linkedin", "gmail_otp_email"): "GMAIL_OTP_EMAIL",
        ("linkedin", "gmail_app_password"): "GMAIL_APP_PASSWORD",
        ("ai", "use_gemini"): "USE_GEMINI",
        ("ai", "gemini_api_key"): "GEMINI_API_KEY",
        ("dashboard_api_key",): "DASHBOARD_API_KEY",
        ("session_encryption_key",): "SESSION_ENCRYPTION_KEY",
    }

    _bool_keys = {("ai", "use_gemini")}

    for keys, env_var in env_map.items():
        env_val = os.environ.get(env_var)
        if not env_val:
            continue
        if len(keys) == 1:
            config[keys[0]] = env_val
        else:
            section, key = keys[0], keys[1]
            if section not in config:
                config[section] = {}
            if (section, key) in _bool_keys:
                config[section][key] = env_val.strip().lower() in ("true", "1", "yes")
            else:
                config[section][key] = env_val

    return config


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Load and return the LinkedIn agent settings (cached singleton).

    Loads linkedin_config.yaml, applies environment variable overrides,
    validates with Pydantic, and ensures data directories exist.
    """
    config = _load_yaml_config()
    config = _apply_env_overrides(config)
    settings = Settings(**config)
    settings.ensure_dirs()
    return settings
