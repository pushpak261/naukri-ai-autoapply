"""
Pydantic settings model for the Naukri Agent.

Loads configuration from config.yaml and merges with environment variable
overrides. Provides typed, validated access to all settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Project root is two levels up from this file (src/config/settings.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Nested config models
# ---------------------------------------------------------------------------
class NaukriCredentials(BaseModel):
    """Naukri.com login credentials."""

    email: str = ""
    password: str = ""
    gmail_otp_email: str = ""
    gmail_app_password: str = ""
    mobile_number: str = ""
    use_otp_login: bool = False


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

    keywords: list[str] = Field(default_factory=lambda: ["Python Developer"])
    locations: list[str] = Field(default_factory=lambda: ["Bangalore"])
    experience_min: int = 0
    experience_max: int = 5
    salary_min: int = 0
    freshness: int = 7
    max_pages: int = 3
    sort_by: str = "relevance"
    enable_heuristics: bool = True

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        allowed = {"relevance", "date"}
        if v not in allowed:
            raise ValueError(f"sort_by must be one of {allowed}")
        return v


class ApplicationSettings(BaseModel):
    """Application behavior controls."""

    daily_cap: int = 25
    match_score_threshold: int = 70
    answer_questions_with_pdf: bool = True
    delay_between_applies_min: int = 30
    delay_between_applies_max: int = 90
    delay_between_actions_min: float = 1.0
    delay_between_actions_max: float = 3.0
    skip_external_apply: bool = True
    collect_external_jobs: bool = True
    email_recipient: str = ""
    dry_run: bool = False
    enable_project_indexer: bool = False
    min_company_rating: float = 3.0


class ProfileSettings(BaseModel):
    """User profile details for auto-filling forms."""

    current_ctc: str = ""
    expected_ctc: str = ""
    notice_period: str = ""
    current_location: str = ""
    preferred_locations: list[str] = Field(default_factory=list)
    total_experience: str = ""


class ExclusionSettings(BaseModel):
    """Filters to skip certain jobs."""

    enable_scam_filter: bool = True
    fake_company_blocklist: list[str] = Field(default_factory=list)
    max_openings_without_logo: int = 50
    companies: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    description_keywords: list[str] = Field(default_factory=list)
    title_whitelist: list[str] = Field(default_factory=list)


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    log_to_file: bool = True
    log_dir: str = "data/logs"


# ---------------------------------------------------------------------------
# Root settings model
# ---------------------------------------------------------------------------
class Settings(BaseModel):
    """Complete application settings loaded from config.yaml + env vars."""

    naukri: NaukriCredentials = Field(default_factory=NaukriCredentials)
    ai: AISettings = Field(default_factory=AISettings)
    resume: ResumeSettings = Field(default_factory=ResumeSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    exclusions: ExclusionSettings = Field(default_factory=ExclusionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # Dashboard API key for frontend authentication
    dashboard_api_key: str = ""
    # Session encryption key (auto-derived from project_root if not set)
    session_encryption_key: str = ""

    # JWT auth settings (auto-generated if not set)
    jwt_secret: str = ""
    jwt_encryption_key: str = ""

    # Computed paths
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    sessions_dir: Path = PROJECT_ROOT / "data" / "sessions"
    resumes_dir: Path = PROJECT_ROOT / "data" / "resumes"
    db_path: Path = PROJECT_ROOT / "data" / "naukri_agent.db"
    run_cap_resets_daily: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def copy_for_run(
        self,
        *,
        cap: int | None = None,
        threshold: int | None = None,
        experience_min: int | None = None,
        experience_max: int | None = None,
    ) -> Settings:
        """Return a shallow copy with per-run overrides applied."""
        data = self.model_dump()
        if cap is not None:
            data["application"]["daily_cap"] = cap
        if threshold is not None:
            data["application"]["match_score_threshold"] = threshold
        if experience_min is not None:
            data["search"]["experience_min"] = experience_min
        if experience_max is not None:
            data["search"]["experience_max"] = experience_max
        copied = Settings(**data)
        copied.run_cap_resets_daily = cap is not None
        return copied

    def ensure_dirs(self) -> None:
        """Create required data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.resumes_dir.mkdir(parents=True, exist_ok=True)
        log_dir = self.project_root / self.logging.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)

    def validate_required(self) -> list[str]:
        """
        Check that the minimum configuration needed to run the agent is
        present, and return a list of human-readable problem descriptions.

        Returns an empty list if everything required is present. Intended to
        be called once at startup (see `src.main`) so the agent fails fast
        with an actionable message instead of crashing deep inside the
        browser-login or AI layers with a confusing stack trace.
        """
        problems: list[str] = []

        if not self.naukri.email:
            problems.append(
                "Naukri email is not set. Set NAUKRI_EMAIL in your .env file "
                "or naukri.email in config.yaml."
            )
        if self.naukri.use_otp_login:
            if not self.naukri.mobile_number:
                problems.append(
                    "Naukri mobile number is not set. Set NAUKRI_MOBILE_NUMBER in your .env "
                    "or naukri.mobile_number in config.yaml for OTP login."
                )
        else:
            if not self.naukri.password:
                problems.append(
                    "Naukri password is not set. Set NAUKRI_PASSWORD in your .env "
                    "or naukri.password in config.yaml."
                )
        if self.ai.use_gemini and not self.ai.gemini_api_key:
            problems.append(
                "Gemini API key is not set. Set GEMINI_API_KEY in your .env "
                "file or ai.gemini_api_key in config.yaml."
            )

        resume_path = self.project_root / self.resume.path if self.resume.path else None
        if not resume_path:
            problems.append("Resume path is not configured (resume.path in config.yaml).")
        elif not resume_path.exists():
            problems.append(f"Resume file not found at: {resume_path}")

        if self.search.experience_min > self.search.experience_max:
            problems.append(
                f"search.experience_min ({self.search.experience_min}) is greater than "
                f"search.experience_max ({self.search.experience_max})."
            )

        return problems


def _load_yaml_config() -> dict:
    """Load the config.yaml file from the project root."""
    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _apply_env_overrides(config: dict) -> dict:
    """
    Override specific config values with environment variables.

    Supported env vars:
        NAUKRI_EMAIL, NAUKRI_PASSWORD, GEMINI_API_KEY
    """
    # Load .env file if it exists
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)

    # Apply overrides
    env_map = {
        ("naukri", "email"): "NAUKRI_EMAIL",
        ("naukri", "password"): "NAUKRI_PASSWORD",
        ("naukri", "gmail_otp_email"): "GMAIL_OTP_EMAIL",
        ("naukri", "gmail_app_password"): "GMAIL_APP_PASSWORD",
        ("naukri", "mobile_number"): "NAUKRI_MOBILE_NUMBER",
        ("naukri", "use_otp_login"): "NAUKRI_USE_OTP_LOGIN",
        ("ai", "use_gemini"): "USE_GEMINI",
        ("ai", "gemini_api_key"): "GEMINI_API_KEY",
        ("dashboard_api_key",): "DASHBOARD_API_KEY",
        ("session_encryption_key",): "SESSION_ENCRYPTION_KEY",
        ("jwt_secret",): "JWT_SECRET",
        ("jwt_encryption_key",): "JWT_ENCRYPTION_KEY",
    }

    # Keys whose values must be coerced from env-var strings to booleans
    _bool_keys = {("naukri", "use_otp_login"), ("ai", "use_gemini")}

    for keys, env_var in env_map.items():
        env_val = os.environ.get(env_var)
        if not env_val:
            continue
        if len(keys) == 1:
            # Flat key directly on config dict
            config[keys[0]] = env_val
        else:
            section, key = keys[0], keys[1]
            if section not in config:
                config[section] = {}
            # Boolean env vars: "true"/"1"/"yes" → True, anything else → False
            if (section, key) in _bool_keys:
                config[section][key] = env_val.strip().lower() in ("true", "1", "yes")
            else:
                config[section][key] = env_val

    return config


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Load and return the application settings (cached singleton).

    Loads config.yaml, applies environment variable overrides, validates
    with Pydantic, and ensures data directories exist.
    """
    config = _load_yaml_config()
    config = _apply_env_overrides(config)
    settings = Settings(**config)
    settings.ensure_dirs()
    return settings


def save_search_experience(experience_min: int, experience_max: int) -> Settings:
    """Persist search experience bounds to config.yaml and return refreshed settings."""
    if experience_min > experience_max:
        raise ValueError(
            f"experience_min ({experience_min}) cannot be greater than "
            f"experience_max ({experience_max})"
        )

    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"config.yaml not found at {config_path}")

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    search = config.setdefault("search", {})
    search["experience_min"] = experience_min
    search["experience_max"] = experience_max

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    get_settings.cache_clear()
    return get_settings()
