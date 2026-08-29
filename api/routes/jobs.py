from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from api.deps import state
from src.naukri_agent.fake_job_detection.rules import evaluate_job_all_filters
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

        # Fetch applications for the whole page in a single query instead of
        # one round-trip per job (was a 1+N query on every /api/jobs call).
        app_by_job_id: dict[int, DBApplication] = {}
        if jobs:
            job_ids = [job.id for job in jobs]
            apps_result = await session.execute(
                select(DBApplication).where(DBApplication.job_id.in_(job_ids))
            )
            app_by_job_id = {app.job_id: app for app in apps_result.scalars().all()}

        items = []
        for job in jobs:
            app = app_by_job_id.get(job.id)
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


class ApplyBatchRequest(BaseModel):
    job_ids: list[int]


@router.get("/api/jobs/inspector")
async def get_jobs_inspector(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=200),
    status_view: str = Query("all", max_length=20),
    source: str = Query("all", max_length=20),
    enable_experience_filter: bool | None = Query(None),
    enable_freshness_filter: bool | None = Query(None),
    enable_scam_filter: bool | None = Query(None),
    enable_title_blacklist: bool | None = Query(None),
    enable_company_blacklist: bool | None = Query(None),
    enable_description_blacklist: bool | None = Query(None),
    enable_heuristics: bool | None = Query(None),
    enable_match_score_filter: bool | None = Query(None),
    master_enable: bool | None = Query(None),
):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        # `total_scraped_raw` must reflect the source-scoped total (search is
        # applied only to the evaluated set below), matching prior behaviour.
        count_stmt = select(func.count(DBJob.id))
        fetch_query = select(DBJob)
        if source and source != "all":
            if source == "naukri":
                src_filter = or_(DBJob.source == "naukri", DBJob.source.is_(None))
            else:
                src_filter = DBJob.source == source
            fetch_query = fetch_query.where(src_filter)
            count_stmt = count_stmt.where(src_filter)

        # Push the free-text search into SQL so we don't load and heuristically
        # evaluate every job just to discard non-matches in Python.
        if search:
            search_filter = or_(
                DBJob.title.ilike(f"%{search}%"),
                DBJob.company.ilike(f"%{search}%"),
                DBJob.location.ilike(f"%{search}%"),
                DBJob.skills.ilike(f"%{search}%"),
            )
            fetch_query = fetch_query.where(search_filter)

        total_scraped_raw = (await session.execute(count_stmt)).scalar_one()
        result = await session.execute(fetch_query.order_by(DBJob.scraped_at.desc()))
        db_jobs = result.scalars().all()

        apps_result = await session.execute(select(DBApplication))
        db_apps = apps_result.scalars().all()
        app_by_job_id = {app.job_id: app for app in db_apps}

        toggles = {}
        if enable_experience_filter is not None:
            toggles["enable_experience_filter"] = enable_experience_filter
        if enable_freshness_filter is not None:
            toggles["enable_freshness_filter"] = enable_freshness_filter
        if enable_scam_filter is not None:
            toggles["enable_scam_filter"] = enable_scam_filter
        if enable_title_blacklist is not None:
            toggles["enable_title_blacklist"] = enable_title_blacklist
        if enable_company_blacklist is not None:
            toggles["enable_company_blacklist"] = enable_company_blacklist
        if enable_description_blacklist is not None:
            toggles["enable_description_blacklist"] = enable_description_blacklist
        if enable_heuristics is not None:
            toggles["enable_heuristics"] = enable_heuristics
        if enable_match_score_filter is not None:
            toggles["enable_match_score_filter"] = enable_match_score_filter
        if master_enable is not None:
            toggles["master_enable"] = master_enable

        all_evaluated_items = []
        total_scraped_raw = len(db_jobs)
        total_passed = 0
        total_rejected = 0
        total_applied = 0
        rejections_by_filter = {
            "experience": 0,
            "freshness": 0,
            "scam_detection": 0,
            "title_blacklist": 0,
            "company_blacklist": 0,
            "description_blacklist": 0,
            "heuristics": 0,
            "match_score": 0,
        }

        from src.naukri_agent.models.entities import Job as EntityJob
        from src.naukri_agent.utils.similarity import VectorSimilarityFilter

        vector_filter = None
        try:
            search_cfg = getattr(state.settings, "search", None)
            kws = getattr(search_cfg, "keywords", []) if search_cfg else []
            vector_filter = VectorSimilarityFilter(kws + ["software", "developer", "engineer", "java", "python", "backend"])
        except Exception:
            pass

        for job in db_jobs:
            app = app_by_job_id.get(job.id)
            match_score = app.match_score if app else None
            is_applied = app and app.status == "applied"

            if is_applied:
                total_applied += 1

            entity_job = EntityJob(
                id=job.id,
                naukri_job_id=job.naukri_job_id,
                title=job.title,
                company=job.company,
                location=job.location,
                experience=job.experience,
                salary=job.salary,
                description=job.description,
                skills=job.skills,
                url=job.url,
                posted_date=job.posted_date,
                openings=job.openings,
                has_company_logo=job.has_company_logo,
            )

            heuristic_score = None
            if vector_filter:
                j_text = f"{job.title or ''} {job.company or ''} {job.skills or ''} {job.description or ''}"
                heuristic_score = vector_filter.get_similarity_score(j_text)

            eval_res = evaluate_job_all_filters(
                entity_job,
                state.settings,
                filter_toggles=toggles,
                match_score=match_score,
                heuristic_score=heuristic_score,
            )

            passed = eval_res["passed"]
            if passed:
                total_passed += 1
            else:
                total_rejected += 1
                for f_key, f_eval in eval_res["filter_evaluations"].items():
                    if f_eval["enabled"] and not f_eval["passed"]:
                        rejections_by_filter[f_key] = rejections_by_filter.get(f_key, 0) + 1

            if status_view == "passed" and not passed:
                continue
            if status_view == "rejected" and passed:
                continue
            if status_view == "applied" and not is_applied:
                continue

            all_evaluated_items.append(
                {
                    "id": job.id,
                    "naukri_job_id": job.naukri_job_id,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "experience": job.experience,
                    "salary": job.salary,
                    "description": (job.description or "")[:250] + ("..." if len(job.description or "") > 250 else ""),
                    "skills": job.skills,
                    "url": job.url,
                    "posted_date": job.posted_date,
                    "openings": job.openings,
                    "has_company_logo": job.has_company_logo,
                    "source": getattr(job, "source", "naukri"),
                    "scraped_at": job.scraped_at.isoformat() if job.scraped_at else "",
                    "passed": passed,
                    "rejection_reasons": eval_res["rejection_reasons"],
                    "filter_evaluations": eval_res["filter_evaluations"],
                    "application": (
                        {
                            "status": app.status,
                            "match_score": app.match_score,
                            "applied_at": app.applied_at.isoformat() if app.applied_at else "",
                        }
                        if app
                        else None
                    ),
                }
            )

        filtered_total = len(all_evaluated_items)
        offset = (page - 1) * per_page
        paginated_items = all_evaluated_items[offset : offset + per_page]

        dummy_job = EntityJob(naukri_job_id="", title="", company="", url="")
        default_eval = evaluate_job_all_filters(dummy_job, state.settings, filter_toggles=toggles)
        active_toggles = {
            f_key: f_val["enabled"]
            for f_key, f_val in default_eval["filter_evaluations"].items()
        }
        active_toggles["master_enable"] = toggles.get("master_enable", True)

        search_cfg = getattr(state.settings, "search", None)
        excl_cfg = getattr(state.settings, "exclusions", None)
        app_cfg = getattr(state.settings, "application", None)

        return {
            "summary": {
                "total_scraped_raw": total_scraped_raw,
                "total_passed": total_passed,
                "total_rejected": total_rejected,
                "total_applied": total_applied,
                "rejections_by_filter": rejections_by_filter,
            },
            "active_toggles": active_toggles,
            "config_limits": {
                "max_experience": getattr(search_cfg, "experience_max", 3) if search_cfg else 3,
                "max_freshness_days": getattr(search_cfg, "freshness", 30) if search_cfg else 30,
                "match_score_threshold": getattr(app_cfg, "match_score_threshold", 40.0) if app_cfg else 40.0,
                "enable_scam_filter": getattr(excl_cfg, "enable_scam_filter", True) if excl_cfg else True,
                "title_keywords_count": len(getattr(excl_cfg, "title_keywords", [])) if excl_cfg else 0,
                "company_blacklist_count": len(getattr(excl_cfg, "companies", [])) if excl_cfg else 0,
                "description_keywords_count": len(getattr(excl_cfg, "description_keywords", [])) if excl_cfg else 0,
            },
            "items": paginated_items,
            "total": filtered_total,
            "page": page,
            "per_page": per_page,
        }


@router.post("/api/jobs/apply-batch")
async def apply_jobs_batch(req: ApplyBatchRequest):
    if not req.job_ids:
        raise HTTPException(status_code=400, detail="No job IDs provided")

    from datetime import UTC, datetime

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        applied_count = 0
        for job_id in req.job_ids:
            job_res = await session.execute(select(DBJob).where(DBJob.id == job_id))
            job = job_res.scalar_one_or_none()
            if not job:
                continue

            app_res = await session.execute(
                select(DBApplication).where(DBApplication.job_id == job_id)
            )
            app = app_res.scalar_one_or_none()

            if app:
                app.status = "applied"
                app.applied_at = datetime.now(UTC)
                if not app.match_score:
                    app.match_score = 85.0
                app.match_reasoning = "Applied via Job Inspector Frontend"
            else:
                new_app = DBApplication(
                    job_id=job_id,
                    status="applied",
                    applied_at=datetime.now(UTC),
                    match_score=85.0,
                    match_reasoning="Applied via Job Inspector Frontend",
                    source=getattr(job, "source", "naukri"),
                )
                session.add(new_app)
            applied_count += 1

        await session.commit()
        return {
            "status": "ok",
            "applied_count": applied_count,
            "message": f"Successfully applied to {applied_count} job(s)",
        }


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


