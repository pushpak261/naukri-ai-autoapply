from fastapi import APIRouter
from sqlalchemy import select

from api.deps import state
from src.naukri_agent.models.db_schema import Job as DBJob
from src.naukri_agent.models.entities import Job as JobEntity
from src.naukri_agent.models.rules import compute_scam_score

router = APIRouter(tags=["scam-detector"])


@router.get("/api/scam-detector/analysis")
async def get_scam_analysis():
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(DBJob).order_by(DBJob.scraped_at.desc()))
        db_jobs = result.scalars().all()

        scored_jobs = []
        for db_job in db_jobs:
            job_entity = JobEntity(
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
            score_result = compute_scam_score(job_entity)
            scored_jobs.append(
                {
                    "job_id": db_job.id,
                    "job_title": db_job.title,
                    "company": db_job.company,
                    "location": db_job.location or "",
                    "skills": db_job.skills or "",
                    "score": score_result.score,
                    "raw_score": score_result.raw_score,
                    "category": score_result.level,
                    "reasons": score_result.reasons,
                }
            )

        # Compute risk distribution
        safe_count = sum(1 for j in scored_jobs if j["category"] == "safe")
        moderate_count = sum(1 for j in scored_jobs if j["category"] == "moderate")
        suspicious_count = sum(1 for j in scored_jobs if j["category"] == "suspicious")

        risk_distribution = [
            {"name": "Safe (0-29)", "value": safe_count, "color": "#22c55e"},
            {"name": "Moderate (30-59)", "value": moderate_count, "color": "#eab308"},
            {"name": "Suspicious (60+)", "value": suspicious_count, "color": "#ef4444"},
        ]

        # Score distribution sorted by score descending
        score_distribution = sorted(scored_jobs, key=lambda j: j["score"], reverse=True)

        # Highest risk listings (top 50)
        highest_risk = score_distribution[:50]

        total_jobs = len(scored_jobs)
        avg_score = (
            round(sum(j["score"] for j in scored_jobs) / total_jobs, 1) if total_jobs > 0 else 0
        )

        return {
            "risk_distribution": risk_distribution,
            "score_distribution": score_distribution,
            "highest_risk": highest_risk,
            "summary": {
                "total_jobs": total_jobs,
                "avg_score": avg_score,
                "safe_count": safe_count,
                "moderate_count": moderate_count,
                "suspicious_count": suspicious_count,
            },
        }
