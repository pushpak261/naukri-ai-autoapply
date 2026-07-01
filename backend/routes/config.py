"""Read-only sanitized config summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.dependencies import get_app_settings
from backend.schemas.job import ConfigSummary
from src.naukri_agent.config.settings import Settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/summary", response_model=ConfigSummary)
async def config_summary(settings: Settings = Depends(get_app_settings)) -> ConfigSummary:
    return ConfigSummary(
        keywords=settings.search.keywords,
        locations=settings.search.locations,
        experience_min=settings.search.experience_min,
        experience_max=settings.search.experience_max,
        daily_cap=settings.application.daily_cap,
        match_score_threshold=settings.application.match_score_threshold,
        dry_run=settings.application.dry_run,
        require_verified_job=settings.application.require_verified_job,
        min_company_rating=settings.application.min_company_rating,
        big_companies=settings.application.big_companies,
        excluded_companies=settings.exclusions.companies,
        excluded_title_keywords=settings.exclusions.title_keywords,
        ai_model=settings.ai.model,
    )
