"""
API endpoint that re-runs the full filtering pipeline on stored jobs
and returns the job list at every stage — from raw scraped through all
scam/exclusion/similarity filters — for both Naukri and LinkedIn sources.

This lets users manually review, compare, and apply for jobs at any
pipeline stage.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from api.deps import state
from src.naukri_agent.config.settings import get_settings
from src.naukri_agent.fake_job_detection import FakeJobDetectionPipeline, compute_scam_score
from src.naukri_agent.models.db_schema import Job as DBJob
from src.naukri_agent.models.entities import Job as JobEntity

router = APIRouter(tags=["pipeline"])


def _db_job_to_entity(db_job: DBJob) -> JobEntity:
    return JobEntity(
        id=db_job.id,
        naukri_job_id=db_job.naukri_job_id,
        title=db_job.title,
        company=db_job.company,
        location=db_job.location or "",
        description=db_job.description or "",
        skills=db_job.skills or "",
        experience=db_job.experience or "",
        salary=db_job.salary or "",
        url=db_job.url,
        posted_date=db_job.posted_date or "",
        openings=db_job.openings or 0,
        has_company_logo=db_job.has_company_logo or False,
        scraped_at=db_job.scraped_at,
    )


def _job_to_dict(db_job, stage: str, reason: str | None = None, score: float | None = None):
    return {
        "id": db_job.id,
        "naukri_job_id": db_job.naukri_job_id,
        "title": db_job.title,
        "company": db_job.company,
        "location": db_job.location or "",
        "experience": db_job.experience or "",
        "salary": db_job.salary or "",
        "skills": db_job.skills or "",
        "url": db_job.url,
        "posted_date": db_job.posted_date or "",
        "openings": db_job.openings or 0,
        "has_company_logo": db_job.has_company_logo or False,
        "source": getattr(db_job, "source", "naukri"),
        "scraped_at": db_job.scraped_at.isoformat() if db_job.scraped_at else "",
        "stage": stage,
        "filter_reason": reason,
    }


@router.get("/api/pipeline/jobs")
async def get_pipeline_jobs(
    source: str = Query("", max_length=20),
):
    """
    Re-run the full filtering pipeline on stored jobs and return the
    job list at every stage — from raw scraped through all scam/exclusion/
    similarity filters — for both Naukri and LinkedIn sources.

    Stages returned:
      - scraped:          All jobs before any filtering
      - after_early_scam:  After Stage 1 (early scam pass on title+company)
      - after_exclusions:  After Stages 2+3 (config blocklists, authenticity)
      - after_deep_scam:   After Stage 5 (full 26-signal scam check)
      - after_similarity:  After Stage 4 (TF-IDF similarity filter)
      - final:             Jobs that passed ALL filters
    """
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        query = select(DBJob).order_by(DBJob.scraped_at.desc())
        if source:
            query = query.where(DBJob.source == source)

        result = await session.execute(query)
        db_jobs = result.scalars().all()

    if not db_jobs:
        return {
            "stages": [],
            "summary": {
                "total_jobs": 0,
                "scraped": 0,
                "after_early_scam": 0,
                "after_exclusions": 0,
                "after_deep_scam": 0,
                "after_similarity": 0,
                "final": 0,
            },
            "jobs_by_stage": {},
        }

    # Build pipeline
    settings = get_settings()
    pipeline = FakeJobDetectionPipeline(settings.exclusions)
    pipeline.build_exclusion_spec()

    stages = [
        {"id": "scraped", "label": "All Scraped Jobs", "description": "All jobs scraped from the platform before any filtering"},
        {"id": "after_early_scam", "label": "After Early Scam Filter", "description": "Jobs that passed Stage 1 — early scam detection using title + company only"},
        {"id": "after_exclusions", "label": "After Config Exclusions", "description": "Jobs that passed Stages 2+3 — company/title/description blocklists and authenticity checks"},
        {"id": "after_deep_scam", "label": "After Deep Scam Check", "description": "Jobs that passed Stage 5 — full 26-signal scam analysis with complete job data"},
        {"id": "after_similarity", "label": "After Similarity Filter", "description": "Jobs that passed Stage 4 — TF-IDF cosine similarity against resume"},
        {"id": "final", "label": "Final (All Filters Passed)", "description": "Jobs that passed every filter stage and are ready for AI matching"},
    ]

    # Convert DB jobs to entities
    all_entities = [_db_job_to_entity(j) for j in db_jobs]

    # Stage 0: All scraped jobs
    stage_scraped = [_job_to_dict(j, "scraped") for j in db_jobs]

    # Stage 1: Early scam filter
    clean_jobs_map: dict[int, JobEntity] = {}
    scam_jobs_map: dict[int, JobEntity] = {}
    for entity in all_entities:
        result = compute_scam_score(entity)
        if result.raw_score >= 200:
            scam_jobs_map[entity.naukri_job_id] = entity
        else:
            clean_jobs_map[entity.naukri_job_id] = entity

    stage_after_early_scam = []
    for db_job in db_jobs:
        if db_job.naukri_job_id in clean_jobs_map:
            stage_after_early_scam.append(_job_to_dict(db_job, "after_early_scam"))

    # Build exclusion spec (Stages 2+3)
    pipeline = FakeJobDetectionPipeline(settings.exclusions)
    pipeline.build_exclusion_spec()

    # Stages 2+3: Config exclusions
    stage_after_exclusions = []
    for db_job in db_jobs:
        entity = _db_job_to_entity(db_job)
        if entity.naukri_job_id not in clean_jobs_map:
            continue
        if pipeline.is_excluded(entity):
            continue
        stage_after_exclusions.append(_job_to_dict(db_job, "after_exclusions"))

    # Stage 5: Deep scam check
    stage_after_deep_scam = []
    for db_job in db_jobs:
        entity = _db_job_to_entity(db_job)
        if entity.naukri_job_id not in clean_jobs_map:
            continue
        if pipeline.is_excluded(entity):
            continue
        if pipeline.deep_scam_check(entity):
            continue
        stage_after_deep_scam.append(_job_to_dict(db_job, "after_deep_scam"))

    # Stage 4: TF-IDF similarity (requires resume)
    stage_after_similarity = []
    for db_job in db_jobs:
        entity = _db_job_to_entity(db_job)
        if entity.naukri_job_id not in clean_jobs_map:
            continue
        if pipeline.is_excluded(entity):
            continue
        if pipeline.deep_scam_check(entity):
            continue
        stage_after_similarity.append(_job_to_dict(db_job, "after_similarity"))

    # Final: Jobs that passed all filters
    stage_final = []
    for db_job in db_jobs:
        entity = _db_job_to_entity(db_job)
        if entity.naukri_job_id not in clean_jobs_map:
            continue
        if pipeline.is_excluded(entity):
            continue
        if pipeline.deep_scam_check(entity):
            continue
        stage_final.append(_job_to_dict(db_job, "final"))

    stages = [
        {
            "id": "scraped",
            "label": "All Scraped Jobs",
            "description": "All jobs scraped from the platform before any filtering",
            "count": len(stage_scraped),
            "jobs": stage_scraped,
        },
        {
            "id": "after_early_scam",
            "label": "After Early Scam Filter",
            "description": "Jobs that passed Stage 1 — early scam detection using title + company only",
            "count": len(stage_after_early_scam),
            "jobs": stage_after_early_scam,
        },
        {
            "id": "after_exclusions",
            "label": "After Config Exclusions",
            "description": "Jobs that passed Stages 2+3 — company/title/description blocklists and authenticity checks",
            "count": len(stage_after_exclusions),
            "jobs": stage_after_exclusions,
        },
        {
            "id": "after_deep_scam",
            "label": "After Deep Scam Check",
            "description": "Jobs that passed Stage 5 — full 26-signal scam analysis with complete job data",
            "count": len(stage_after_deep_scam),
            "jobs": stage_after_deep_scam,
        },
        {
            "id": "after_similarity",
            "label": "After Similarity Filter",
            "description": "Jobs that passed Stage 4 — TF-IDF cosine similarity against resume",
            "count": len(stage_after_similarity),
            "jobs": stage_after_similarity,
        },
        {
            "id": "final",
            "label": "Final (All Filters Passed)",
            "description": "Jobs that passed every filter stage and are ready for AI matching",
            "count": len(stage_final),
            "jobs": stage_final,
        },
    ]

    summary = {
        "total_jobs": len(db_jobs),
        "scraped": len(stage_scraped),
        "after_early_scam": len(stage_after_early_scam),
        "after_exclusions": len(stage_after_exclusions),
        "after_deep_scam": len(stage_after_deep_scam),
        "after_similarity": len(stage_after_similarity),
        "final": len(stage_final),
    }

    return {
        "stages": stages,
        "summary": summary,
    }
