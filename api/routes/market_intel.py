import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from api.deps import state
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob

router = APIRouter(tags=["market-intel"])


@router.get("/api/market-intel/salary-benchmarks")
async def salary_benchmarks():
    """Compare expected CTC to market rates from job listings with salary data."""
    from sqlalchemy import select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(DBJob.salary, DBJob.title, DBJob.company, DBJob.location)
            .where(DBJob.salary.isnot(None))
            .where(DBJob.salary != "")
            .limit(200)
        )
        rows = result.all()

    salaries = []
    for salary, title, company, location in rows:
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*(?:Lakh|L|lac|k|K)?", str(salary))
        if len(nums) >= 2:
            low, high = float(nums[0]), float(nums[1])
            avg = (low + high) / 2
            salaries.append(
                {
                    "title": title or "Unknown",
                    "company": company or "Unknown",
                    "location": location or "Unknown",
                    "low": low,
                    "high": high,
                    "avg": round(avg, 1),
                    "raw": salary,
                }
            )

    avg_market = round(sum(s["avg"] for s in salaries) / len(salaries), 1) if salaries else 0
    return {
        "items": salaries[:50],
        "summary": {
            "total_listings": len(salaries),
            "average_market_ctc": avg_market,
            "min_market_ctc": round(min(s["avg"] for s in salaries), 1) if salaries else 0,
            "max_market_ctc": round(max(s["avg"] for s in salaries), 1) if salaries else 0,
        },
    }


@router.get("/api/market-intel/skill-demand")
async def skill_demand():
    """Which skills yield highest match scores."""
    from sqlalchemy import select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(DBJob.skills, DBApplication.match_score)
            .join(DBApplication, DBApplication.job_id == DBJob.id)
            .where(DBApplication.match_score.isnot(None))
        )
        rows = result.all()

    skill_scores: dict[str, list[int]] = {}
    for skills_str, score in rows:
        if not skills_str:
            continue
        for skill in re.split(r"[,\|]", str(skills_str)):
            skill = skill.strip().lower()
            if len(skill) > 2:
                if skill not in skill_scores:
                    skill_scores[skill] = []
                skill_scores[skill].append(int(score) if score else 0)

    items = [
        {
            "skill": skill,
            "count": len(scores),
            "avg_score": round(sum(scores) / len(scores), 1),
            "max_score": max(scores),
        }
        for skill, scores in sorted(skill_scores.items(), key=lambda x: len(x[1]), reverse=True)
        if len(scores) >= 2
    ]
    return {"items": items[:100]}


@router.get("/api/market-intel/competitor-companies")
async def competitor_companies():
    """Companies your profile most often matches against."""
    from sqlalchemy import func, select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(
                DBJob.company,
                func.avg(DBApplication.match_score).label("avg_score"),
                func.count(DBApplication.id).label("count"),
            )
            .join(DBApplication, DBApplication.job_id == DBJob.id)
            .where(DBApplication.match_score.isnot(None))
            .group_by(DBJob.company)
            .order_by(func.count(DBApplication.id).desc())
            .limit(30)
        )
        companies = [
            {
                "company": row[0] or "Unknown",
                "avg_match_score": round(float(row[1]), 1) if row[1] else 0,
                "application_count": row[2],
            }
            for row in result.all()
        ]
        return {"items": companies}


@router.get("/api/market-intel/win-rate-prediction")
async def win_rate_prediction():
    """Simple prediction of application success based on match score brackets."""
    from sqlalchemy import case, func, select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        brackets = [(0, 30), (30, 50), (50, 70), (70, 85), (85, 101)]
        items = []
        for low, high in brackets:
            result = await session.execute(
                select(
                    func.count(DBApplication.id).label("total"),
                    func.sum(case((DBApplication.status == "applied", 1), else_=0)).label(
                        "applied_count"
                    ),
                )
                .where(DBApplication.match_score >= low)
                .where(DBApplication.match_score < high)
            )
            row = result.one()
            total = row.total or 0
            applied = row.applied_count or 0
            rate = round((applied / total * 100), 1) if total > 0 else 0
            items.append(
                {
                    "bracket": f"{low}-{high - 1}",
                    "total": total,
                    "applied": applied,
                    "success_rate": rate,
                }
            )
        return {"items": items}
