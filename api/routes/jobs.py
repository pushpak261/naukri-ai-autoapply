from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from api.deps import state
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs")
async def get_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=200),
    status: str = Query("", max_length=50),
    sort: str = Query("newest", max_length=20),
    match_score_min: float = Query(0, ge=0, le=100),
    match_score_max: float = Query(100, ge=0, le=100),
    source: str = Query("", max_length=20),
):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        query = select(DBJob)
        count_query = select(func.count(DBJob.id))

        if sort == "newest":
            query = query.order_by(DBJob.scraped_at.desc())
        elif sort == "oldest":
            query = query.order_by(DBJob.scraped_at)
        elif sort in ("score_asc", "score_desc"):
            query = query.outerjoin(DBApplication, DBApplication.job_id == DBJob.id)
            order_col = (
                DBApplication.match_score.asc()
                if sort == "score_asc"
                else DBApplication.match_score.desc()
            )
            query = query.order_by(order_col)

        filters = []
        if source:
            filters.append(DBJob.source == source)
        if search:
            search_filter = or_(
                DBJob.title.ilike(f"%{search}%"),
                DBJob.company.ilike(f"%{search}%"),
                DBJob.location.ilike(f"%{search}%"),
                DBJob.skills.ilike(f"%{search}%"),
            )
            filters.append(search_filter)

        if status:
            subq = select(DBApplication.job_id).where(DBApplication.status == status).subquery()
            filters.append(DBJob.id.in_(subq))

        if match_score_min > 0 or match_score_max < 100:
            subq = (
                select(DBApplication.job_id)
                .where(
                    DBApplication.match_score >= match_score_min,
                    DBApplication.match_score <= match_score_max,
                )
                .subquery()
            )
            filters.append(DBJob.id.in_(subq))

        if filters:
            combined = filters[0]
            for f in filters[1:]:
                combined = combined & f
            query = query.where(combined)
            count_query = count_query.where(combined)

        total = (await session.execute(count_query)).scalar_one()
        offset = (page - 1) * per_page
        result = await session.execute(query.offset(offset).limit(per_page))
        jobs = result.scalars().all()

        items = []
        for job in jobs:
            app_result = await session.execute(
                select(DBApplication).where(DBApplication.job_id == job.id)
            )
            app = app_result.scalar_one_or_none()
            items.append(
                {
                    "id": job.id,
                    "naukri_job_id": job.naukri_job_id,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "experience": job.experience,
                    "salary": job.salary,
                    "skills": job.skills,
                    "url": job.url,
                    "posted_date": job.posted_date,
                    "openings": job.openings,
                    "has_company_logo": job.has_company_logo,
                    "source": getattr(job, "source", "naukri"),
                    "scraped_at": job.scraped_at.isoformat() if job.scraped_at else "",
                    "application_status": app.status if app else None,
                    "match_score": app.match_score if app else None,
                }
            )

        return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: int):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(DBJob).where(DBJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        app_result = await session.execute(
            select(DBApplication).where(DBApplication.job_id == job.id)
        )
        app = app_result.scalar_one_or_none()

        return {
            "id": job.id,
            "naukri_job_id": job.naukri_job_id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "experience": job.experience,
            "salary": job.salary,
            "description": job.description,
            "skills": job.skills,
            "url": job.url,
            "posted_date": job.posted_date,
            "openings": job.openings,
            "has_company_logo": job.has_company_logo,
            "source": getattr(job, "source", "naukri"),
            "scraped_at": job.scraped_at.isoformat() if job.scraped_at else "",
            "application": (
                {
                    "match_score": app.match_score,
                    "status": app.status,
                    "match_reasoning": app.match_reasoning,
                    "matching_skills": app.matching_skills,
                    "missing_skills": app.missing_skills,
                    "error_message": app.error_message,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else "",
                }
                if app
                else None
            ),
        }
