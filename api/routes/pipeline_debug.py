"""
Job Pipeline Debug — read-only view of all scraped jobs before and after filtering,
with per-job filter reasons, for both Naukri and LinkedIn sources.

This endpoint does NOT modify any data or affect the existing application workflow.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from api.deps import state
from src.naukri_agent.config.settings import get_settings
from src.naukri_agent.fake_job_detection import FakeJobDetectionPipeline, compute_scam_score
from src.naukri_agent.fake_job_detection.rules import (
    EARLY_SCAM_THRESHOLD,
    SCAM_THRESHOLD,
    _HIDDEN_COMPANY_RE,
    AuthenticityExclusionSpecification,
    CompanyExclusionSpecification,
    DescriptionExclusionSpecification,
    TitleExclusionSpecification,
)
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob
from src.naukri_agent.models.entities import Job as JobEntity
from src.naukri_agent.utils.filters import JobFilter
from src.naukri_agent.utils.similarity import VectorSimilarityFilter

router = APIRouter(tags=["pipeline-debug"])

# ---------------------------------------------------------------------------
# Domain exclusion patterns (mirrors NaukriAgent._is_job_in_excluded_domain)
# ---------------------------------------------------------------------------
NON_DEV_ROLES = [
    "qa ", "qa engineer", "qa analyst", "qa tester",
    "test automation", "test engineer", "automation tester",
    "manual tester", "software tester", "etl tester",
    "support engineer", "technical support",
    "data analyst", "data engineer", "data scientist",
    "business analyst", "business associate",
    "ui designer", "ux designer", "graphic designer",
    "web designer", "wordpress",
    "appium", "selenium",
    "intern",
    "associate lead", "project manager",
]

DEV_KEYWORDS = [
    "developer", "engineer", "full stack", "fullstack", "backend",
    "frontend", "front end", "back end", "java", "python", "react",
    "angular", "node", "spring", "dot net", ".net", "c#", "csharp",
    "software", "application", "web developer", "programmer",
    "microservices", "api", "tech lead", "technology",
]

FILTER_CATEGORIES = [
    "experience_mismatch",
    "freshness",
    "early_scam",
    "company_exclusion",
    "title_exclusion",
    "description_exclusion",
    "authenticity",
    "duplicate",
    "deep_scam",
    "domain_exclusion",
    "similarity_low",
]

FILTER_LABELS: dict[str, str] = {
    "experience_mismatch": "Experience Mismatch",
    "freshness": "Job Too Old",
    "early_scam": "Early Scam Detected",
    "company_exclusion": "Company Blocklisted",
    "title_exclusion": "Title Blocked",
    "description_exclusion": "Description Blocked",
    "authenticity": "Authenticity Check Failed",
    "duplicate": "Already Applied",
    "deep_scam": "Scam/Consultancy Detected",
    "domain_exclusion": "Non-Dev Role",
    "similarity_low": "Low Similarity Score",
}

SIMILARITY_THRESHOLD = 0.10


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


def _job_to_debug_dict(
    db_job: DBJob,
    filter_reason: str | None = None,
    filter_category: str | None = None,
    scam_reasons: list[str] | None = None,
) -> dict[str, Any]:
    source = getattr(db_job, "source", None) or "naukri"
    return {
        "id": db_job.id,
        "title": db_job.title,
        "company": db_job.company,
        "location": db_job.location or "",
        "experience": db_job.experience or "",
        "salary": db_job.salary or "",
        "skills": db_job.skills or "",
        "url": db_job.url,
        "posted_date": db_job.posted_date or "",
        "openings": db_job.openings or 0,
        "source": source,
        "scraped_at": db_job.scraped_at.isoformat() if db_job.scraped_at else "",
        "filter_reason": filter_reason,
        "filter_category": filter_category,
        "scam_details": scam_reasons,
    }


def _is_job_in_excluded_domain(job: JobEntity) -> bool:
    if not job or not job.title:
        return False
    title_lower = job.title.lower()
    if any(role in title_lower for role in NON_DEV_ROLES):
        return True
    if any(kw in title_lower for kw in DEV_KEYWORDS):
        return False
    return True


def _build_vector_filter(
    db_jobs: list[DBJob],
) -> tuple[VectorSimilarityFilter | None, bool]:
    settings = get_settings()
    resume_path = settings.project_root / "resume_profile.json"
    if not resume_path.exists():
        return None, False
    try:
        profile_data = json.loads(resume_path.read_text(encoding="utf-8"))
        if not profile_data:
            return None, False
        summary = profile_data.get("summary") or ""
        tech_skills = profile_data.get("technical_skills", []) or []
        if not summary and not tech_skills:
            return None, False
        text_blocks = [summary] + tech_skills

        all_texts: list[str] = []
        for j in db_jobs:
            txt = f"{j.title} {j.company} {j.skills or ''} {j.description or ''}"
            all_texts.append(txt)

        doc_frequencies: dict[str, int] = {}
        tokenizer = VectorSimilarityFilter([""])
        for txt in all_texts:
            words = set(tokenizer._tokenize(txt))
            for w in words:
                doc_frequencies[w] = doc_frequencies.get(w, 0) + 1

        return VectorSimilarityFilter(text_blocks, doc_frequencies, len(all_texts)), True
    except Exception:
        return None, False


@router.get("/api/pipeline/debug")
async def get_pipeline_debug(
    source: str = Query("", max_length=20),
):
    """
    Read-only pipeline debug endpoint.

    Loads all scraped jobs from the database and simulates every filtering stage
    in order. Returns jobs before filtering, after filtering, and every job that
    was filtered out with the specific reason.

    Filter stages checked (in order):
      1. Experience mismatch  — job requires more experience than configured max
      2. Freshness            — job posting is older than configured max days
      3. Early scam           — scam score >= 200 using title + company only
      4. Company blocklist    — company name matches configured blocklist
      5. Title exclusion      — title contains blocked keywords
      6. Description exclusion— description contains blocked keywords
      7. Authenticity         — hidden company name, no logo + high openings
      8. Duplicate            — already applied (same title + company)
      9. Deep scam            — scam score >= 80 with full job data
     10. Domain exclusion     — non-development role / non-matching tech stack
     11. Similarity low       — TF-IDF similarity below 0.10 threshold

    Does NOT modify any data. Pure read-only.
    """
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        query = select(DBJob).order_by(DBJob.scraped_at.desc())
        if source:
            query = query.where(DBJob.source == source)
        result = await session.execute(query)
        db_jobs = result.scalars().all()

        apps_result = await session.execute(
            select(DBJob.title, DBJob.company).join(
                DBApplication, DBApplication.job_id == DBJob.id
            )
        )
        existing_apps = apps_result.all()

    if not db_jobs:
        return {
            "summary": {
                "total_scraped": 0,
                "passed_all_filters": 0,
                "filtered_out": 0,
            },
            "filter_breakdown": {cat: 0 for cat in FILTER_CATEGORIES},
            "filter_labels": FILTER_LABELS,
            "pre_filter": [],
            "post_filter": [],
            "filtered_out": [],
        }

    settings = get_settings()

    # Build filter components
    job_filter = JobFilter(
        max_experience=settings.search.experience_max,
        max_freshness_days=settings.search.freshness,
        sort_by=settings.search.sort_by,
    )
    company_exclusion = CompanyExclusionSpecification(settings.exclusions.companies)
    title_exclusion = TitleExclusionSpecification(settings.exclusions.title_keywords)
    desc_exclusion = DescriptionExclusionSpecification(settings.exclusions.description_keywords)
    auth_exclusion = AuthenticityExclusionSpecification(
        settings.exclusions.fake_company_blocklist,
        settings.exclusions.max_openings_without_logo,
    )

    # Build dedup lookup (JOIN: applications -> jobs for title + company)
    already_applied: set[tuple[str, str]] = set()
    for title, company in existing_apps:
        t = (title or "").lower().strip()
        c = (company or "").lower().strip()
        if t and c:
            already_applied.add((t, c))

    # Build TF-IDF vector filter
    vector_filter, resume_available = _build_vector_filter(db_jobs)

    pre_filter: list[dict[str, Any]] = []
    post_filter: list[dict[str, Any]] = []
    filtered_out: list[dict[str, Any]] = []
    filter_breakdown: dict[str, int] = {cat: 0 for cat in FILTER_CATEGORIES}
    scam_cache: dict[str, Any] = {}

    for db_job in db_jobs:
        entity = _db_job_to_entity(db_job)
        pre_filter.append(_job_to_debug_dict(db_job))

        filter_category: str | None = None
        filter_reason: str | None = None
        scam_details: list[str] | None = None

        # 1. Experience filter
        if filter_category is None and not job_filter._passes_experience_filter(entity.experience):
            filter_category = "experience_mismatch"
            filter_reason = f"Requires '{entity.experience}' which exceeds max {settings.search.experience_max} years"

        # 2. Freshness filter
        if filter_category is None and not job_filter._passes_freshness_filter(entity.posted_date):
            filter_category = "freshness"
            filter_reason = f"Posted '{entity.posted_date}' exceeds {settings.search.freshness} day limit"

        # 3. Early scam check (Stage 1)
        if filter_category is None:
            scam_result = compute_scam_score(entity)
            scam_cache[entity.naukri_job_id or str(entity.id)] = scam_result
            if scam_result.raw_score >= EARLY_SCAM_THRESHOLD:
                filter_category = "early_scam"
                filter_reason = f"Early scam detected (score: {scam_result.raw_score})"
                scam_details = scam_result.reasons

        # 4. Company exclusion
        if filter_category is None and company_exclusion.is_satisfied_by(entity):
            filter_category = "company_exclusion"
            filter_reason = f"Company '{entity.company}' is in blocklist"

        # 5. Title exclusion
        if filter_category is None and title_exclusion.is_satisfied_by(entity):
            filter_category = "title_exclusion"
            filter_reason = f"Title contains blocked keyword(s)"

        # 6. Description exclusion
        if filter_category is None and desc_exclusion.is_satisfied_by(entity):
            filter_category = "description_exclusion"
            filter_reason = "Description contains blocked keyword(s)"

        # 7. Authenticity
        if filter_category is None and auth_exclusion.is_satisfied_by(entity):
            filter_category = "authenticity"
            if entity.company and _HIDDEN_COMPANY_RE.match(entity.company.strip()):
                filter_reason = f"Hidden/generic company name '{entity.company}'"
            elif not entity.has_company_logo and entity.openings >= settings.exclusions.max_openings_without_logo:
                filter_reason = f"No company logo with {entity.openings} openings (max {settings.exclusions.max_openings_without_logo})"
            else:
                filter_reason = "Failed authenticity check"

        # 8. Duplicate check
        if filter_category is None:
            key = (entity.title.lower().strip(), entity.company.lower().strip())
            if key in already_applied:
                filter_category = "duplicate"
                filter_reason = f"Already applied to '{entity.title}' at '{entity.company}'"

        # 9. Deep scam check (Stage 5)
        if filter_category is None:
            deep_result = scam_cache.get(entity.naukri_job_id or str(entity.id)) or compute_scam_score(entity)
            if deep_result.raw_score >= SCAM_THRESHOLD:
                filter_category = "deep_scam"
                filter_reason = f"Scam/consultancy detected (score: {deep_result.raw_score})"
                scam_details = deep_result.reasons

        # 10. Domain exclusion
        if filter_category is None and _is_job_in_excluded_domain(entity):
            title_lower = entity.title.lower()
            non_dev = [r for r in NON_DEV_ROLES if r in title_lower]
            if non_dev:
                filter_reason = f"Non-development role: matches '{non_dev[0].strip()}'"
            else:
                filter_reason = "Title does not match development role keywords"
            filter_category = "domain_exclusion"

        # 11. TF-IDF similarity
        if filter_category is None and resume_available and vector_filter:
            full_text = f"{entity.title} {entity.company} {entity.skills or ''} {entity.description or ''}"
            score = vector_filter.get_similarity_score(full_text)
            if score < SIMILARITY_THRESHOLD:
                filter_category = "similarity_low"
                filter_reason = f"TF-IDF similarity score ({score:.3f}) below {SIMILARITY_THRESHOLD} threshold"

        if filter_category is not None:
            filter_breakdown[filter_category] += 1
            filtered_out.append(_job_to_debug_dict(db_job, filter_reason, filter_category, scam_details))
        else:
            post_filter.append(_job_to_debug_dict(db_job))

    return {
        "summary": {
            "total_scraped": len(pre_filter),
            "passed_all_filters": len(post_filter),
            "filtered_out": len(filtered_out),
        },
        "filter_breakdown": filter_breakdown,
        "filter_labels": FILTER_LABELS,
        "pre_filter": pre_filter,
        "post_filter": post_filter,
        "filtered_out": filtered_out,
    }
