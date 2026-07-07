from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import state

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
    delay_between_applies_min: int | None = None
    delay_between_applies_max: int | None = None


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
        },
        "logging": {
            "level": s.logging.level,
            "log_to_file": s.logging.log_to_file,
        },
    }


@router.put("/api/config")
async def update_config(update: ConfigUpdate):
    from src.naukri_agent.config.settings import get_settings
    from src.naukri_agent.config.store import apply_updates

    updates: list[tuple[list[str], Any, bool]] = [
        (["naukri", "email"], update.naukri_email, True),
        (["naukri", "password"], update.naukri_password, True),
        (["ai", "gemini_api_key"], update.gemini_api_key, True),
        (["ai", "model"], update.ai_model, False),
        (["ai", "enable_matching"], update.enable_matching, False),
        (["ai", "use_gemini"], update.use_gemini, False),
        (["application", "daily_cap"], update.daily_cap, False),
        (["application", "match_score_threshold"], update.match_score_threshold, False),
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
        (["application", "delay_between_applies_min"], update.delay_between_applies_min, False),
        (["application", "delay_between_applies_max"], update.delay_between_applies_max, False),
    ]

    apply_updates([(keys, value) for keys, value, _is_secret in updates if value is not None])

    get_settings.cache_clear()
    import api.deps

    api.deps.state.settings = get_settings()

    return {"status": "ok", "message": "Configuration updated"}
