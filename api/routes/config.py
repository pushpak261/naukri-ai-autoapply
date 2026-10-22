from typing import Any, Annotated, Literal

import asyncio
import yaml
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from api.deps import state
from libs.common.security import encrypt_value

router = APIRouter(tags=["config"])

class ConfigUpdate(BaseModel):
    naukri_email: str | None = None
    naukri_password: str | None = None
    gemini_api_key: str | None = None
    ai_model: str | None = None
    enable_matching: bool | None = None
    use_gemini: bool | None = None
    daily_cap: int | None = None
    match_score_threshold: int | None = None
    search_keywords: list[str] | None = None
    search_locations: list[str] | None = None
    experience_min: int | None = None
    experience_max: int | None = None
    salary_min: int | None = None
    freshness: int | None = None
    max_pages: int | None = None
    sort_by: str | None = None
    enable_heuristics: bool | None = None
    skip_external_apply: bool | None = None
    dry_run: bool | None = None
    answer_questions_with_pdf: bool | None = None
    current_ctc: str | None = None
    expected_ctc: str | None = None
    notice_period: str | None = None
    current_location: str | None = None
    preferred_locations: list[str] | None = None
    total_experience: str | None = None
    employment_status: Literal["", "employed", "unemployed", "student"] | None = None
    serving_notice: bool | None = None
    last_working_date: str | None = None
    confirmed_answers: dict[str, str] | None = Field(default=None, max_length=100)
    skill_experience_years: dict[str, Annotated[float, Field(ge=0, le=80, allow_inf_nan=False)]] | None = Field(default=None, max_length=100)
    delay_between_applies_min: int | None = None
    delay_between_applies_max: int | None = None
    # Retry settings (feature 3)
    max_retries: int | None = None
    # Rate limit settings (feature 10)
    rate_limit_capacity: float | None = None
    rate_limit_refill_rate: float | None = None
    # Notification settings (feature 7)
    email_notifications_enabled: bool | None = None
    email_recipient: str | None = None
    notify_on_apply: bool | None = None
    notify_on_failure: bool | None = None
    notify_on_scam: bool | None = None
    notify_on_match: bool | None = None
    enable_scam_filter: bool | None = None

    @field_validator("last_working_date")
    @classmethod
    def validate_last_working_date(cls, value):
        if value:
            from datetime import date
            date.fromisoformat(value)
        return value

def _set_nested(d: dict, keys: list[str], value: Any) -> None:
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value

@router.get("/api/config")
async def get_config():
    s = state.settings
    return {
        "naukri": {
            "email": s.naukri.email[:3] + "..." if s.naukri.email else "",
            "has_password": bool(s.naukri.password),
            "use_otp_login": s.naukri.use_otp_login,
            "mobile_number": s.naukri.mobile_number or "",
        },
        "ai": {
            "use_gemini": s.ai.use_gemini,
            "enable_matching": s.ai.enable_matching,
            "has_api_key": bool(s.ai.gemini_api_key),
            "model": s.ai.model,
            "fallback_model": s.ai.fallback_model,
            "abort_on_quota": s.ai.abort_on_quota,
            "temperature": s.ai.temperature,
            "max_output_tokens": s.ai.max_output_tokens,
        },
        "resume": {
            "path": s.resume.path,
        },
        "search": {
            "keywords": s.search.keywords,
            "locations": s.search.locations,
            "experience_min": s.search.experience_min,
            "experience_max": s.search.experience_max,
            "salary_min": s.search.salary_min,
            "freshness": s.search.freshness,
            "max_pages": s.search.max_pages,
            "sort_by": s.search.sort_by,
            "enable_heuristics": s.search.enable_heuristics,
        },
        "application": {
            "daily_cap": s.application.daily_cap,
            "match_score_threshold": s.application.match_score_threshold,
            "max_retries": s.application.max_retries,
            "answer_questions_with_pdf": s.application.answer_questions_with_pdf,
            "delay_between_applies_min": s.application.delay_between_applies_min,
            "delay_between_applies_max": s.application.delay_between_applies_max,
            "skip_external_apply": s.application.skip_external_apply,
            "dry_run": s.application.dry_run,
            "enable_project_indexer": s.application.enable_project_indexer,
        },
        "profile": {
            "current_ctc": s.profile.current_ctc,
            "expected_ctc": s.profile.expected_ctc,
            "notice_period": s.profile.notice_period,
            "current_location": s.profile.current_location,
            "preferred_locations": s.profile.preferred_locations,
            "total_experience": s.profile.total_experience,
            "confirmed_answers": s.profile.confirmed_answers,
            "employment_status": s.profile.employment_status,
            "serving_notice": s.profile.serving_notice,
            "last_working_date": s.profile.last_working_date,
            "skill_experience_years": s.profile.skill_experience_years,
        },
        "logging": {
            "level": s.logging.level,
            "log_to_file": s.logging.log_to_file,
        },
        "notifications": {
            "email_notifications_enabled": (
                s.application.get("email_notifications_enabled", False)
                if isinstance(s.application, dict)
                else getattr(s.application, "email_notifications_enabled", False)
            ),
            "email_recipient": (
                s.application.get("email_recipient", "")
                if isinstance(s.application, dict)
                else getattr(s.application, "email_recipient", "")
            ),
            "notify_on_apply": (
                s.application.get("notify_on_apply", True)
                if isinstance(s.application, dict)
                else getattr(s.application, "notify_on_apply", True)
            ),
            "notify_on_failure": (
                s.application.get("notify_on_failure", True)
                if isinstance(s.application, dict)
                else getattr(s.application, "notify_on_failure", True)
            ),
            "notify_on_scam": (
                s.application.get("notify_on_scam", True)
                if isinstance(s.application, dict)
                else getattr(s.application, "notify_on_scam", True)
            ),
            "notify_on_match": (
                s.application.get("notify_on_match", False)
                if isinstance(s.application, dict)
                else getattr(s.application, "notify_on_match", False)
            ),
        },
        "rate_limits": {
            "rate_limit_capacity": (
                s.application.get("rate_limit_capacity", 10.0)
                if isinstance(s.application, dict)
                else getattr(s.application, "rate_limit_capacity", 10.0)
            ),
            "rate_limit_refill_rate": (
                s.application.get("rate_limit_refill_rate", 1.0)
                if isinstance(s.application, dict)
                else getattr(s.application, "rate_limit_refill_rate", 1.0)
            ),
        },
    }

@router.put("/api/config")
async def update_config(update: ConfigUpdate):
    from src.naukri_agent.config.settings import get_settings

    config_path = state.settings.project_root / "config.yaml"
    if not config_path.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="config.yaml not found")

    text = await asyncio.to_thread(config_path.read_text, encoding="utf-8")
    config_data = yaml.safe_load(text) or {}

    updates: list[tuple[list[str], Any, bool]] = [
        (["naukri", "email"], update.naukri_email, True),
        (["naukri", "password"], update.naukri_password, True),
        (["ai", "gemini_api_key"], update.gemini_api_key, True),
        (["ai", "model"], update.ai_model, False),
        (["ai", "enable_matching"], update.enable_matching, False),
        (["ai", "use_gemini"], update.use_gemini, False),
        (["application", "daily_cap"], update.daily_cap, False),
        (["application", "match_score_threshold"], update.match_score_threshold, False),
        (["application", "max_retries"], update.max_retries, False),
        (["search", "keywords"], update.search_keywords, False),
        (["search", "locations"], update.search_locations, False),
        (["search", "experience_min"], update.experience_min, False),
        (["search", "experience_max"], update.experience_max, False),
        (["search", "salary_min"], update.salary_min, False),
        (["search", "freshness"], update.freshness, False),
        (["search", "max_pages"], update.max_pages, False),
        (["search", "sort_by"], update.sort_by, False),
        (["search", "enable_heuristics"], update.enable_heuristics, False),
        (["application", "skip_external_apply"], update.skip_external_apply, False),
        (["application", "dry_run"], update.dry_run, False),
        (["application", "answer_questions_with_pdf"], update.answer_questions_with_pdf, False),
        (["profile", "current_ctc"], update.current_ctc, False),
        (["profile", "expected_ctc"], update.expected_ctc, False),
        (["profile", "notice_period"], update.notice_period, False),
        (["profile", "current_location"], update.current_location, False),
        (["profile", "preferred_locations"], update.preferred_locations, False),
        (["profile", "total_experience"], update.total_experience, False),
        (["profile", "employment_status"], update.employment_status, False),
        (["profile", "serving_notice"], update.serving_notice, False),
        (["profile", "last_working_date"], update.last_working_date, False),
        (["profile", "confirmed_answers"], update.confirmed_answers, False),
        (["profile", "skill_experience_years"], update.skill_experience_years, False),
        (["application", "delay_between_applies_min"], update.delay_between_applies_min, False),
        (["application", "delay_between_applies_max"], update.delay_between_applies_max, False),
        (["application", "email_notifications_enabled"], update.email_notifications_enabled, False),
        (["application", "email_recipient"], update.email_recipient, False),
        (["application", "notify_on_apply"], update.notify_on_apply, False),
        (["application", "notify_on_failure"], update.notify_on_failure, False),
        (["application", "notify_on_scam"], update.notify_on_scam, False),
        (["application", "notify_on_match"], update.notify_on_match, False),
        (["application", "rate_limit_capacity"], update.rate_limit_capacity, False),
        (["application", "rate_limit_refill_rate"], update.rate_limit_refill_rate, False),
        (["exclusions", "enable_scam_filter"], update.enable_scam_filter, False),
    ]

    for keys, value, is_secret in updates:
        if value is not None or (keys == ["profile", "serving_notice"] and "serving_notice" in update.model_fields_set):
            if is_secret:
                env_var_map: dict[tuple[str, ...], str] = {
                    ("naukri", "email"): "NAUKRI_EMAIL",
                    ("naukri", "password"): "NAUKRI_PASSWORD",
                    ("ai", "gemini_api_key"): "GEMINI_API_KEY",
                }
                env_var = env_var_map.get(tuple(keys))
                if env_var:
                    # Keep the password encrypted at rest in config.yaml.
                    if tuple(keys) == ("naukri", "password"):
                        value = encrypt_value(value)
                    _set_nested(config_data, keys, value)
            else:
                _set_nested(config_data, keys, value)

    await asyncio.to_thread(
        config_path.write_text,
        yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )

    from api.tenants import reload_current_settings
    # AI preferences are shared by both agents; remove stale per-platform overrides.
    ai_changes = {key: value for key, value in {'gemini_api_key': update.gemini_api_key,
        'model': update.ai_model, 'use_gemini': update.use_gemini,
        'enable_matching': update.enable_matching}.items() if value is not None}
    platform_path = state.settings.project_root / 'linkedin_config.yaml'
    if ai_changes and platform_path.exists():
        platform_config = yaml.safe_load(platform_path.read_text(encoding='utf-8')) or {}
        if isinstance(platform_config.get('ai'), dict):
            for key in ai_changes:
                platform_config['ai'].pop(key, None)
            platform_path.write_text(yaml.safe_dump(platform_config), encoding='utf-8')
    reload_current_settings()

    return {"status": "ok", "message": "Configuration updated"}


@router.get('/api/ai/status')
async def ai_status():
    ai = state.settings.ai
    return {'configured': bool(ai.gemini_api_key), 'enabled': ai.use_gemini,
            'model': ai.model, 'matching_enabled': ai.enable_matching,
            'features': {'resume': 'AI on request', 'matching': 'AI when enabled',
                         'screening_answers': 'AI when enabled', 'copilot': 'evidence rules plus on-demand Gemini advice',
                         'resume_improvement': 'on-demand Gemini advice', 'skills_gap': 'on-demand Gemini learning plan',
                         'scam_review': 'risk signals plus on-demand Gemini review',
                         'market': 'saved-listing statistics plus on-demand Gemini interpretation',
                         'analytics': 'measured database statistics plus on-demand Gemini interpretation'}}


@router.post('/api/ai/test')
async def test_ai_connection():
    from fastapi import HTTPException
    from src.naukri_agent.ai.llm_provider import GeminiProvider
    ai = state.settings.ai
    if not ai.gemini_api_key:
        raise HTTPException(422, 'Save your Gemini API key in AI Settings first.')
    provider = GeminiProvider(ai.gemini_api_key, ai.model)
    try:
        await asyncio.wait_for(provider.generate_content('Reply only with OK. This is a connectivity test.', max_output_tokens=32), timeout=25)
    except Exception:
        raise HTTPException(503, 'AI connection failed. Check the key, model access, network and Gemini quota. No resume was sent.') from None
    finally:
        from contextlib import suppress
        with suppress(Exception):
            await provider.aclose()
    return {'status': 'ok', 'model': provider._model_name, 'message': 'AI connection verified. No resume was sent.'}


# ---------------------------------------------------------------------------
# LinkedIn Config Endpoints
# ---------------------------------------------------------------------------
LINKEDIN_CONFIG_PATH = None  # resolved at runtime

def _get_linkedin_config_path():
    return state.settings.project_root / "linkedin_config.yaml"

@router.get("/api/config/linkedin")
async def get_linkedin_config():
    """Read the LinkedIn agent configuration."""
    import os
    from pathlib import Path

    from libs.common.workspace_config import load_linkedin_workspace_config
    config_data = load_linkedin_workspace_config(state.settings.project_root)

    if state.user_id:
        from libs.common.workspace_config import load_linkedin_workspace_config
        from src.linked_agent.config.settings import Settings as LinkedInSettings
        config_data = LinkedInSettings(**load_linkedin_workspace_config(state.settings.project_root)).model_dump()

    # Check .env for credentials
    env_email = os.environ.get("LINKEDIN_EMAIL", "") if not state.user_id else ""
    env_password = os.environ.get("LINKEDIN_PASSWORD", "") if not state.user_id else ""

    linkedin = config_data.get("linkedin", {})
    ai = config_data.get("ai", {})
    resume = config_data.get("resume", {})
    search = config_data.get("search", {})
    application = config_data.get("application", {})

    return {
        "configured": bool(linkedin.get("email") or env_email),
        "email": (linkedin.get("email") or env_email)[:3] + "..." if (linkedin.get("email") or env_email) else "",
        "has_password": bool(linkedin.get("password") or env_password),
        "two_factor_code": bool(linkedin.get("two_factor_code")),
        "ai": {
            "use_gemini": ai.get("use_gemini", False),
            "has_api_key": bool(ai.get("gemini_api_key")),
            "model": ai.get("model", "gemini-2.5-flash"),
            "enable_matching": ai.get("enable_matching", True),
        },
        "resume": {
            "path": resume.get("path", ""),
            "exists": bool((state.settings.project_root / resume.get("path", "")).exists()) if resume.get("path") else False,
        },
        "search": {
            "keywords": search.get("keywords", []),
            "locations": search.get("locations", []),
            "work_type": search.get("work_type", ""),
            "freshness": search.get("freshness", "past_week"),
            "max_pages": search.get("max_pages", 25),
            "sort_by": search.get("sort_by", "date"),
        },
        "application": {
            "daily_cap": application.get("daily_cap", 150),
            "match_score_threshold": application.get("match_score_threshold", 40),
            "easy_apply_only": application.get("easy_apply_only", True),
            "dry_run": application.get("dry_run", False),
        },
    }

class LinkedInConfigUpdate(BaseModel):
    linkedin_email: str | None = None
    linkedin_password: str | None = None
    linkedin_2fa_code: str | None = None
    search_keywords: list[str] | None = None
    search_locations: list[str] | None = None
    work_type: str | None = None
    freshness: str | None = None
    max_pages: int | None = None
    sort_by: str | None = None
    daily_cap: int | None = None
    match_score_threshold: int | None = None
    easy_apply_only: bool | None = None
    dry_run: bool | None = None
    resume_path: str | None = None

@router.put("/api/config/linkedin")
async def update_linkedin_config(update: LinkedInConfigUpdate):
    """Update the LinkedIn agent configuration (linkedin_config.yaml + .env)."""
    from pathlib import Path

    config_path = _get_linkedin_config_path()
    config_data = {}
    if config_path.exists():
        text = await asyncio.to_thread(config_path.read_text, encoding="utf-8")
        config_data = yaml.safe_load(text) or {}

    # Ensure sections exist
    config_data.setdefault("linkedin", {})
    config_data.setdefault("ai", {})
    config_data.setdefault("resume", {})
    config_data.setdefault("search", {})
    config_data.setdefault("application", {})

    # Credentials go to .env (more secure)
    env_path = state.settings.project_root / ".env"
    env_lines = []
    if env_path.exists():
        env_lines = (await asyncio.to_thread(env_path.read_text, encoding="utf-8")).splitlines()

    def _set_env(key: str, value: str) -> None:
        nonlocal env_lines
        found = False
        for i, line in enumerate(env_lines):
            if line.startswith(f"{key}="):
                env_lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            env_lines.append(f"{key}={value}")

    if update.linkedin_email is not None:
        _set_env("LINKEDIN_EMAIL", update.linkedin_email)
        config_data["linkedin"]["email"] = update.linkedin_email
    if update.linkedin_password is not None:
        _set_env("LINKEDIN_PASSWORD", update.linkedin_password)
        config_data["linkedin"]["password"] = encrypt_value(update.linkedin_password)
    if update.linkedin_2fa_code is not None:
        config_data["linkedin"]["two_factor_code"] = update.linkedin_2fa_code

    if update.search_keywords is not None:
        config_data["search"]["keywords"] = update.search_keywords
    if update.search_locations is not None:
        config_data["search"]["locations"] = update.search_locations
    if update.work_type is not None:
        config_data["search"]["work_type"] = update.work_type
    if update.freshness is not None:
        config_data["search"]["freshness"] = update.freshness
    if update.max_pages is not None:
        config_data["search"]["max_pages"] = update.max_pages
    if update.sort_by is not None:
        config_data["search"]["sort_by"] = update.sort_by
    if update.daily_cap is not None:
        config_data["application"]["daily_cap"] = update.daily_cap
    if update.match_score_threshold is not None:
        config_data["application"]["match_score_threshold"] = update.match_score_threshold
    if update.easy_apply_only is not None:
        config_data["application"]["easy_apply_only"] = update.easy_apply_only
    if update.dry_run is not None:
        config_data["application"]["dry_run"] = update.dry_run
    if update.resume_path is not None:
        if state.user_id and update.resume_path:
            from fastapi import HTTPException
            target = (state.settings.project_root / update.resume_path).resolve()
            if not target.is_relative_to(state.settings.resumes_dir.resolve()):
                raise HTTPException(422, "Choose a resume uploaded to your account")
        config_data["resume"]["path"] = update.resume_path

    # Write .env
    if not state.user_id:
        await asyncio.to_thread(env_path.write_text, "\n".join(env_lines) + "\n", encoding="utf-8")

    # Write linkedin_config.yaml
    await asyncio.to_thread(
        config_path.write_text,
        yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Drop the cached settings and refresh the shared runtime state so the new
    # values take effect immediately instead of on the next restart.
    from src.naukri_agent.config.settings import get_settings

    from api.tenants import reload_current_settings
    reload_current_settings()

    return {"status": "ok", "message": "LinkedIn configuration updated"}
