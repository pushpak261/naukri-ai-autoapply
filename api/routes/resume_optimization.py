"""
REST endpoint for resume optimization analysis.
Aggregates resume profile, applications, match cache, and job data
into a single comprehensive analysis for the Skills Gap / Resume Optimization page.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import select

from api.deps import state
from src.naukri_agent.models.db_schema import Application as DBApplication
from src.naukri_agent.models.db_schema import Job as DBJob

router = APIRouter(tags=["resume-optimization"])


def _parse_skills(skills_val: str | list | None) -> list[str]:
    """Parse skills from various formats into a list of strings."""
    if not skills_val:
        return []
    if isinstance(skills_val, list):
        return [s.strip() for s in skills_val if s and s.strip()]
    if isinstance(skills_val, str):
        skills_val = skills_val.strip()
        if not skills_val:
            return []
        # Try JSON array
        if skills_val.startswith("["):
            try:
                parsed = json.loads(skills_val)
                if isinstance(parsed, list):
                    return [s.strip() for s in parsed if s and s.strip()]
            except (json.JSONDecodeError, TypeError):
                pass
        # Try comma-separated
        if "," in skills_val:
            return [s.strip() for s in skills_val.split(",") if s.strip()]
        # Single value
        return [skills_val]
    return []


@router.get("/api/resume-optimization/analysis")
async def get_resume_optimization():
    # 1. Load resume profile
    profile_json_path: Path = state.settings.project_root / "resume_profile.json"
    resume_profile = None
    if profile_json_path.exists():
        try:
            resume_profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    resume_skills: list[str] = []
    if resume_profile:
        raw_skills = resume_profile.get("skills") or resume_profile.get("technical_skills") or []
        if isinstance(raw_skills, list):
            resume_skills = [s.strip().lower() for s in raw_skills if s and s.strip()]
        elif isinstance(raw_skills, str):
            resume_skills = [s.strip().lower() for s in raw_skills.split(",") if s.strip()]

    # 2. Load all applications
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        apps_result = await session.execute(
            select(DBApplication, DBJob)
            .join(DBJob, DBApplication.job_id == DBJob.id)
            .order_by(DBApplication.applied_at.desc())
        )
        app_rows = apps_result.all()

    # 3. Build skill analysis from applications
    skill_map: dict[str, dict[str, int]] = {}
    for app, job in app_rows:
        matching = _parse_skills(app.matching_skills)
        missing = _parse_skills(app.missing_skills)
        for s in matching:
            key = s.lower()
            if key not in skill_map:
                skill_map[key] = {"matching": 0, "missing": 0, "total": 0, "display": s}
            skill_map[key]["matching"] += 1
            skill_map[key]["total"] += 1
        for s in missing:
            key = s.lower()
            if key not in skill_map:
                skill_map[key] = {"matching": 0, "missing": 0, "total": 0, "display": s}
            skill_map[key]["missing"] += 1
            skill_map[key]["total"] += 1

    # Also add skills from job listings themselves as additional reference
    async with session_factory() as session:
        jobs_result = await session.execute(select(DBJob))
        all_jobs = jobs_result.scalars().all()

    # 4. Compute keyword density from job listings vs resume
    keyword_counts: dict[str, int] = {}
    for job in all_jobs:
        text = f"{job.title or ''} {job.company or ''} {job.skills or ''}".lower()
        words = [w for w in text.split() if len(w) > 3]
        seen = set()
        for w in words:
            if w not in seen:
                keyword_counts[w] = keyword_counts.get(w, 0) + 1
                seen.add(w)

    resume_keywords = set(resume_skills)
    keyword_density = []
    for kw, count in sorted(keyword_counts.items(), key=lambda x: -x[1]):
        if count >= 3 and (count / len(all_jobs) * 100) > 10 if all_jobs else False:
            your_count = 1 if kw in resume_keywords else 0
            freq_pct = round(count / len(all_jobs) * 100) if all_jobs else 0
            gap = freq_pct - (your_count * 50)
            keyword_density.append(
                {
                    "keyword": kw,
                    "count": count,
                    "avgInListings": freq_pct,
                    "yourCount": your_count,
                    "gap": gap,
                }
            )
    keyword_density = sorted(keyword_density, key=lambda x: -x["gap"])[:15]

    # 5. Build skills breakdown
    skills_data = []
    for key, val in sorted(skill_map.items(), key=lambda x: -x[1]["total"]):
        match_rate = round((val["matching"] / val["total"]) * 100) if val["total"] > 0 else 0
        skills_data.append(
            {
                "skill": val["display"],
                "matching": val["matching"],
                "missing": val["missing"],
                "total": val["total"],
                "matchRate": match_rate,
            }
        )
    skills_data = skills_data[:20]

    # 6. Compute ATS score
    ats_score = 0
    ats_label = "N/A"
    if skills_data:
        avg_rate = sum(s["matchRate"] for s in skills_data) / len(skills_data)
        total_matching = sum(s["matching"] for s in skills_data)
        total_missing = sum(s["missing"] for s in skills_data)
        coverage = (
            total_matching / (total_matching + total_missing)
            if (total_matching + total_missing) > 0
            else 1
        )
        ats_score = min(100, round(avg_rate * 0.6 + coverage * 100 * 0.4))
        ats_label = "Strong" if ats_score >= 80 else "Moderate" if ats_score >= 50 else "Needs Work"

    # 7. Skill coverage breakdown
    level_ranges = [
        {"name": "Strong", "min": 80, "color": "#22c55e"},
        {"name": "Moderate", "min": 50, "color": "#eab308"},
        {"name": "Weak", "min": 0, "color": "#ef4444"},
    ]
    skill_breakdown = []
    for r in level_ranges:
        count = sum(
            1
            for s in skills_data
            if s["matchRate"] >= r["min"] and (r["min"] == 0 or s["matchRate"] < r["min"] + 30)
        )
        skill_breakdown.append({"name": r["name"], "count": count, "color": r["color"]})

    # 8. Resume info
    resume_info = None
    if resume_profile:
        resume_info = {
            "exists": True,
            "name": resume_profile.get("name", ""),
            "email": resume_profile.get("email", ""),
            "skills_count": len(resume_skills),
            "total_experience_years": resume_profile.get("total_experience_years", 0),
        }
    else:
        resume_info = {
            "exists": False,
            "name": "",
            "email": "",
            "skills_count": 0,
            "total_experience_years": 0,
        }

    return {
        "resume": resume_info,
        "skills_data": skills_data,
        "keyword_density": keyword_density,
        "skill_breakdown": skill_breakdown,
        "ats": {"score": ats_score, "label": ats_label},
        "summary": {
            "total_applications": len(app_rows),
            "total_jobs": len(all_jobs),
            "total_skills_analyzed": len(skills_data),
            "has_resume": resume_profile is not None,
        },
    }
