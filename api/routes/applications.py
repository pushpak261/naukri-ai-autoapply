from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from api.deps import state
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob
from src.naukri_agent.models.db_schema import RunLog as DBRunLog

router = APIRouter(tags=["applications"])


@router.get("/api/applications")
async def get_applications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str = Query("", max_length=50),
    sort: str = Query("newest", max_length=20),
):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        query = select(DBApplication)
        count_query = select(func.count(DBApplication.id))

        if sort == "newest":
            query = query.order_by(DBApplication.applied_at.desc())
        elif sort == "oldest":
            query = query.order_by(DBApplication.applied_at)
        elif sort == "score_desc":
            query = query.order_by(DBApplication.match_score.desc())
        elif sort == "score_asc":
            query = query.order_by(DBApplication.match_score)

        if status:
            query = query.where(DBApplication.status == status)
            count_query = count_query.where(DBApplication.status == status)

        total = (await session.execute(count_query)).scalar_one()
        offset = (page - 1) * per_page
        result = await session.execute(query.offset(offset).limit(per_page))
        apps = result.scalars().all()

        items = []
        for app in apps:
            job_result = await session.execute(select(DBJob).where(DBJob.id == app.job_id))
            job = job_result.scalar_one_or_none()
            items.append(
                {
                    "id": app.id,
                    "job_id": app.job_id,
                    "job_title": job.title if job else "Unknown",
                    "company": job.company if job else "Unknown",
                    "location": job.location if job else "",
                    "url": job.url if job else "",
                    "match_score": app.match_score,
                    "status": app.status,
                    "match_reasoning": app.match_reasoning,
                    "matching_skills": app.matching_skills,
                    "missing_skills": app.missing_skills,
                    "error_message": app.error_message,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else "",
                }
            )

        return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/api/run-logs")
async def get_run_logs(limit: int = Query(10, ge=1, le=100)):
    logs = await state.repo.get_run_stats(limit=limit)
    return {"items": logs}


@router.get("/api/run-logs/{run_id}/jobs")
async def get_run_jobs(run_id: int):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        run_result = await session.execute(select(DBRunLog).where(DBRunLog.id == run_id))
        run_log = run_result.scalar_one_or_none()
        if not run_log:
            raise HTTPException(status_code=404, detail="Run log not found")

        cutoff = run_log.started_at
        result = await session.execute(
            select(DBApplication, DBJob)
            .join(DBJob, DBApplication.job_id == DBJob.id)
            .where(DBApplication.applied_at >= cutoff)
            .order_by(DBApplication.applied_at.desc())
        )
        items = []
        for app, job in result.all():
            items.append(
                {
                    "job_title": job.title,
                    "company": job.company,
                    "match_score": app.match_score,
                    "status": app.status,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else "",
                    "matching_skills": app.matching_skills,
                    "missing_skills": app.missing_skills,
                }
            )
        return {
            "items": items,
            "run": {
                "id": run_log.id,
                "started_at": run_log.started_at.isoformat() if run_log.started_at else "",
                "keywords": run_log.search_keywords,
                "status": run_log.status,
            },
        }
