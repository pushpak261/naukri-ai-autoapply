from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select

from api.deps import state
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob

router = APIRouter(tags=["stats"])


@router.get("/api/stats")
async def get_stats(days: int = Query(7, ge=1, le=365), source: str = Query("", max_length=20)):
    s = state.settings
    r = state.repo
    stats = await r.get_application_stats(days=days)
    today_count = await r.get_today_application_count()
    run_logs = await r.get_run_stats(limit=10)
    recent = await r.get_recent_applications(limit=5)

    total_jobs_found = sum(rw.get("found", 0) for rw in run_logs)

    # Compute totals from the applications table (source of truth)
    # instead of summing run_logs which is only updated at cleanup and
    # can be stale if runs are interrupted or in-progress.
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        base_filters = []
        if source:
            base_filters.append(DBApplication.source == source)

        # All-time totals computed in a single aggregate query (was 3 separate
        # count queries — one round-trip instead of three).
        counts_q = select(
            func.count(DBApplication.id),
            func.sum(case((DBApplication.status == "applied", 1), else_=0)),
            func.sum(case((DBApplication.status.like("skipped%"), 1), else_=0)),
        )
        if base_filters:
            counts_q = counts_q.where(*base_filters)
        total_c, applied_c, skipped_c = (await session.execute(counts_q)).one()
        total_applied = applied_c or 0
        total_skipped = skipped_c or 0
        total_failed = (total_c or 0) - total_applied - total_skipped

    return {
        "stats": stats,
        "today_applied": today_count,
        "total_jobs_found": total_jobs_found,
        "total_applied": total_applied,
        "total_skipped": total_skipped,
        "total_failed": total_failed,
        "recent_applications": recent,
        "recent_runs": run_logs,
        "daily_cap": s.application.daily_cap,
        "match_threshold": s.application.match_score_threshold,
    }


@router.get("/api/analytics/company-distribution")
async def company_distribution(limit: int = Query(15, ge=1, le=50)):
    from sqlalchemy import func, select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(DBJob.company, func.count(DBApplication.id).label("count"))
            .join(DBApplication, DBApplication.job_id == DBJob.id)
            .group_by(DBJob.company)
            .order_by(func.count(DBApplication.id).desc())
            .limit(limit)
        )
        companies = [{"company": row[0], "count": row[1]} for row in result.all()]
        return {"items": companies}


@router.get("/api/analytics/location-distribution")
async def location_distribution():
    from sqlalchemy import func, select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(DBJob.location, func.count(DBApplication.id).label("count"))
            .join(DBApplication, DBApplication.job_id == DBJob.id)
            .group_by(DBJob.location)
            .order_by(func.count(DBApplication.id).desc())
        )
        locations = [{"location": row[0] or "Unknown", "count": row[1]} for row in result.all()]
        return {"items": locations}


@router.get("/api/analytics/keyword-performance")
async def keyword_performance(days: int = Query(365, ge=1, le=365)):
    import re

    from sqlalchemy import select

    since = datetime.now(UTC) - timedelta(days=days)
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(DBJob, DBApplication)
            .join(DBApplication, DBApplication.job_id == DBJob.id)
            .where(DBApplication.applied_at >= since)
        )
        rows = result.all()
        keyword_stats: dict[str, dict[str, int]] = {}
        for db_job, db_app in rows:
            text = f"{db_job.title} {db_job.description}"
            words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
            for kw in state.settings.search.keywords:
                kw_words = set(re.findall(r"\b[a-zA-Z]+\b", kw.lower()))
                if kw_words and kw_words & words:
                    if kw not in keyword_stats:
                        keyword_stats[kw] = {"found": 0, "applied": 0, "skipped": 0, "failed": 0}
                    keyword_stats[kw]["found"] += 1
                    if db_app.status == "applied":
                        keyword_stats[kw]["applied"] += 1
                    elif db_app.status.startswith("skipped"):
                        keyword_stats[kw]["skipped"] += 1
                    elif db_app.status in ("failed", "error"):
                        keyword_stats[kw]["failed"] += 1

        items = [
            {"keyword": k, **v}
            for k, v in sorted(keyword_stats.items(), key=lambda x: x[1]["found"], reverse=True)
        ]
        return {"items": items}


@router.get("/api/analytics/daily-timeline")
async def daily_timeline(days: int = Query(30, ge=1, le=365)):
    from sqlalchemy import func, select

    since = datetime.now(UTC) - timedelta(days=days)
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(
                func.date(DBApplication.applied_at).label("date"),
                DBApplication.status,
                func.count(DBApplication.id).label("count"),
            )
            .where(DBApplication.applied_at >= since)
            .where(DBApplication.applied_at.isnot(None))
            .group_by(func.date(DBApplication.applied_at), DBApplication.status)
            .order_by(func.date(DBApplication.applied_at))
        )
        daily: dict[str, dict[str, int]] = {}
        for row in result.all():
            d = str(row.date)
            if d not in daily:
                daily[d] = {"applied": 0, "skipped": 0, "failed": 0, "total": 0}
            if row.status == "applied":
                daily[d]["applied"] += row.count
            elif row.status.startswith("skipped"):
                daily[d]["skipped"] += row.count
            else:
                daily[d]["failed"] += row.count
            daily[d]["total"] += row.count

        items = [{"date": d, **v} for d, v in sorted(daily.items())]
        return {"items": items}


@router.get("/api/analytics/success-rate-trend")
async def success_rate_trend(days: int = Query(30, ge=1, le=365)):
    from sqlalchemy import case, func, select

    since = datetime.now(UTC) - timedelta(days=days)
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(
                func.date(DBApplication.applied_at).label("date"),
                func.count(DBApplication.id).label("total"),
                func.sum(case((DBApplication.status == "applied", 1), else_=0)).label(
                    "applied_count"
                ),
            )
            .where(DBApplication.applied_at >= since)
            .where(DBApplication.applied_at.isnot(None))
            .group_by(func.date(DBApplication.applied_at))
            .order_by(func.date(DBApplication.applied_at))
        )

        items = []
        for row in result.all():
            total = row.total or 0
            applied_count = row.applied_count or 0
            rate = (applied_count / total * 100) if total > 0 else 0
            items.append(
                {
                    "date": str(row.date),
                    "total": total,
                    "applied": applied_count,
                    "success_rate": round(rate, 1),
                }
            )
        return {"items": items}


@router.get("/api/application-statuses")
async def get_application_statuses():
    return {
        "statuses": [
            {"value": "applied", "label": "Applied", "color": "green"},
            {"value": "skipped_low_score", "label": "Skipped (Low Score)", "color": "yellow"},
            {"value": "skipped_excluded", "label": "Skipped (Excluded)", "color": "orange"},
            {
                "value": "skipped_already_applied",
                "label": "Skipped (Already Applied)",
                "color": "gray",
            },
            {"value": "skipped_external", "label": "Skipped (External)", "color": "purple"},
            {"value": "skipped_screening", "label": "Skipped (Screening)", "color": "blue"},
            {"value": "skipped_dry_run", "label": "Skipped (Dry Run)", "color": "teal"},
            {"value": "uncertain", "label": "Uncertain", "color": "yellow"},
            {"value": "failed", "label": "Failed", "color": "red"},
            {"value": "error", "label": "Error", "color": "red"},
        ]
    }
