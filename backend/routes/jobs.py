"""Job listing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.dependencies import get_repository
from backend.schemas.job import JobCard, JobListResponse
from src.naukri_agent.database.repository import SQLAlchemyRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
async def list_jobs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
    repo: SQLAlchemyRepository = Depends(get_repository),
) -> JobListResponse:
    rows, total = await repo.get_jobs_paginated(offset=offset, limit=limit, status=status)
    items = [
        JobCard(
            id=row.get("id"),
            naukri_job_id=row.get("naukri_job_id", ""),
            title=row.get("title", ""),
            company=row.get("company", ""),
            location=row.get("location", ""),
            experience=row.get("experience", ""),
            salary=row.get("salary", ""),
            url=row.get("url", ""),
            posted_date=row.get("posted_date", ""),
            skills=row.get("skills", ""),
            status=row.get("status"),
            match_score=row.get("match_score"),
            match_reasoning=row.get("match_reasoning"),
            applied_at=row.get("applied_at"),
        )
        for row in rows
    ]
    return JobListResponse(items=items, total=total, offset=offset, limit=limit)
