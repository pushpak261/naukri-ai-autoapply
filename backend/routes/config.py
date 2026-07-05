"""Config summary and search filter endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_app_settings
from backend.schemas.config import SearchExperienceUpdate
from backend.schemas.job import ConfigSummary
from src.naukri_agent.config.settings import Settings, save_search_experience

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
        min_company_rating=settings.application.min_company_rating,
        excluded_companies=settings.exclusions.companies,
        excluded_title_keywords=settings.exclusions.title_keywords,
        ai_model=settings.ai.model,
    )


@router.put("/search/experience", response_model=ConfigSummary)
async def update_search_experience(body: SearchExperienceUpdate) -> ConfigSummary:
    try:
        settings = save_search_experience(body.experience_min, body.experience_max)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ConfigSummary(
        keywords=settings.search.keywords,
        locations=settings.search.locations,
        experience_min=settings.search.experience_min,
        experience_max=settings.search.experience_max,
        daily_cap=settings.application.daily_cap,
        match_score_threshold=settings.application.match_score_threshold,
        dry_run=settings.application.dry_run,
        min_company_rating=settings.application.min_company_rating,
        excluded_companies=settings.exclusions.companies,
        excluded_title_keywords=settings.exclusions.title_keywords,
        ai_model=settings.ai.model,
    )
