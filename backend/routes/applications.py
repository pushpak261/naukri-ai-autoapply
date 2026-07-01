"""Application history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.dependencies import get_repository
from backend.schemas.job import ApplicationRecord
from src.naukri_agent.database.repository import SQLAlchemyRepository

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("/recent", response_model=list[ApplicationRecord])
async def recent_applications(
    limit: int = Query(20, ge=1, le=100),
    repo: SQLAlchemyRepository = Depends(get_repository),
) -> list[ApplicationRecord]:
    rows = await repo.get_recent_applications(limit=limit)
    return [
        ApplicationRecord(
            job_title=row.get("job_title", ""),
            company=row.get("company", ""),
            location=row.get("location", ""),
            match_score=row.get("match_score", 0.0),
            status=row.get("status", ""),
            applied_at=row.get("applied_at", ""),
            url=row.get("url", ""),
            error_message=row.get("error_message", ""),
        )
        for row in rows
    ]
