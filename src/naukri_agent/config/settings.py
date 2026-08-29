"""
Pydantic settings model for the Naukri Agent.

Loads configuration from config.yaml and merges with environment variable
overrides. Provides typed, validated access to all settings.
"""

from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Project root is two levels up from this file (src/config/settings.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _decrypt_secret(value: str) -> str:
    """Decrypt a ``enc:<token>`` secret (mirrors ``libs.common.security`` keying).

    Values without the ``enc:`` prefix are returned unchanged so plaintext
    (e.g. provided via env) keeps working. Key resolution matches
    ``libs.common.security.resolve_encryption_key`` so the two round-trip.
    """
    if not value or not value.startswith("enc:"):
        return value
    raw = os.environ.get("SESSION_ENCRYPTION_KEY") or f"local-{PROJECT_ROOT}"
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    try:
        return Fernet(key).decrypt(value[len("enc:") :].encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Nested config models
# ---------------------------------------------------------------------------
class NaukriCredentials(BaseModel):
    """Naukri.com login credentials."""

    email: str = ""
    password: str = ""

    @field_validator("password", mode="before")
    @classmethod
    def _decrypt_password(cls, v: object) -> object:
        return _decrypt_secret(v) if isinstance(v, str) else v
    gmail_otp_email: str = ""
    gmail_app_password: str = ""
    mobile_number: str = ""
    name: str = ""
    use_otp_login: bool = False


class AISettings(BaseModel):
    """Gemini AI configuration."""

    use_gemini: bool = True
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
    # Notification settings (feature 7)
    email_notifications_enabled: bool = False
    notify_on_apply: bool = True
    notify_on_failure: bool = True
    notify_on_scam: bool = True
    notify_on_match: bool = False
    # Retry settings (feature 3)
    max_retries: int = 3
    # Re-application cooldown (days): after this many days an already-applied
    # job becomes eligible again, so refreshed/reposted listings get re-applied
    # and interview chances stay high. Set to 0 to block forever (legacy behavior).
    reapply_after_days: int = 30
    # Rate limiter settings (feature 10)
    rate_limit_capacity: float = 10.0
    rate_limit_refill_rate: float = 1.0


class ProfileSettings(BaseModel):
    """User profile details for auto-filling forms."""

    current_ctc: str = ""
    expected_ctc: str = ""
    notice_period: str = ""
    current_location: str = ""
    preferred_locations: list[str] = Field(default_factory=list)
    total_experience: str = ""
    github_url: str = ""
    linkedin_url: str = ""
    languages: list[str] = Field(default_factory=lambda: ["English"])
    willing_to_relocate: bool = True
    preferred_work_mode: str = "Hybrid"
    reason_for_change: str = ""
    date_of_birth: str = ""
    marital_status: str = ""


class ExclusionSettings(BaseModel):
    """Filters to skip certain jobs."""

    enable_scam_filter: bool = False
    fake_company_blocklist: list[str] = Field(default_factory=list)
    max_openings_without_logo: int = 50
    companies: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    description_keywords: list[str] = Field(default_factory=list)


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

        load_dotenv(env_path, override=False)

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
                config[section][key] = env_val

    # Auto-enable use_gemini if GEMINI_API_KEY is set and USE_GEMINI wasn't explicitly disabled
    if os.environ.get("GEMINI_API_KEY") and not os.environ.get("USE_GEMINI"):
        if "ai" not in config:
            config["ai"] = {}
        config["ai"]["use_gemini"] = True

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
