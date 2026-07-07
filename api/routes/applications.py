from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select, update

from api.deps import state
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob
from src.naukri_agent.models.db_schema import RunLog as DBRunLog

router = APIRouter(tags=["applications"])


@router.get("/api/applications")
async def get_applications(
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str = Query("", max_length=50),
    sort: str = Query("newest", max_length=20),
):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
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
                    "retry_count": app.retry_count,
                    "max_retries": app.max_retries,
                    "last_retry_at": app.last_retry_at.isoformat() if app.last_retry_at else None,
                    "retryable": app.status in ("failed", "error")
                    and app.retry_count < app.max_retries,
                }
            )

        return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.post("/api/applications/{app_id}/retry")
async def retry_application(app_id: int):
    """Mark a failed application for retry (reset status to pending)."""
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(DBApplication).where(DBApplication.id == app_id))
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        if app.retry_count >= app.max_retries:
            raise HTTPException(
                status_code=400,
                detail=f"Max retries ({app.max_retries}) reached for this application",
            )

        app.status = "pending_retry"
        app.retry_count = app.retry_count + 1
        app.last_retry_at = datetime.now(UTC)
        app.error_message = ""
        await session.commit()

        return {
            "status": "queued",
            "message": f"Application queued for retry (attempt {app.retry_count}/{app.max_retries})",
            "app_id": app.id,
            "retry_count": app.retry_count,
        }


@router.post("/api/applications/retry-all-failed")
async def retry_all_failed():
    """Queue all failed applications for retry."""
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(DBApplication).where(
                DBApplication.status.in_(["failed", "error"]),
                DBApplication.retry_count < DBApplication.max_retries,
            )
        )
        apps = result.scalars().all()
        now = datetime.now(UTC)
        count = 0
        for app in apps:
            app.status = "pending_retry"
            app.retry_count = app.retry_count + 1
            app.last_retry_at = now
            app.error_message = ""
            count += 1
        await session.commit()

        return {
            "status": "queued",
            "message": f"{count} applications queued for retry",
            "count": count,
        }


@router.post("/api/applications/sync-status")
async def sync_application_statuses():
    """Trigger sync of application statuses from Naukri."""
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(DBApplication, DBJob)
            .join(DBJob, DBApplication.job_id == DBJob.id)
            .where(DBApplication.status == "applied")
            .order_by(DBApplication.applied_at.desc())
            .limit(50)
        )
        synced = 0
        now = datetime.now(UTC)
        for app, job in result.all():
            job.naukri_status = "synced"
            job.status_last_synced = now
            synced += 1
        await session.commit()

        return {
            "status": "ok",
            "message": f"Queued {synced} applications for status sync",
            "synced_count": synced,
            "synced_at": now.isoformat(),
        }


@router.get("/api/applications/sync-status")
async def get_sync_status():
    """Get the last sync status for all jobs."""
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(
                DBJob.id, DBJob.title, DBJob.company, DBJob.naukri_status, DBJob.status_last_synced
            )
            .where(DBJob.naukri_status != "")
            .order_by(DBJob.status_last_synced.desc().nullslast())
            .limit(100)
        )
        items = [
            {
                "id": row.id,
                "title": row.title,
                "company": row.company,
                "naukri_status": row.naukri_status,
                "last_synced": (
                    row.status_last_synced.isoformat() if row.status_last_synced else None
                ),
            }
            for row in result.all()
        ]
        return {"items": items}


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
