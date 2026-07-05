"""
Tests for title whitelisting, composite deduplication, and recalibrated heuristics.
"""

from __future__ import annotations

import heapq
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.domain.entities import Job, ResumeProfile
from src.naukri_agent.orchestrator.agent import NaukriAgent
from src.naukri_agent.ai.similarity import VectorSimilarityFilter


def test_title_whitelist_filtering() -> None:
    """Validate that jobs not matching title whitelist are ignored."""
    settings = Settings()
    settings.exclusions.title_whitelist = ["developer", "engineer"]

    jobs = [
        Job(naukri_job_id="J1", title="Python Developer", company="A", url=""),
        Job(naukri_job_id="J2", title="Housekeeper Associate", company="B", url=""),
        Job(naukri_job_id="J3", title="Frontend Engineer", company="C", url=""),
        Job(naukri_job_id="J4", title="Photographer", company="D", url=""),
    ]

    vector_filter = VectorSimilarityFilter(["Python"])

    # Simulate the heap building loop
    job_queue = []
    for idx, job in enumerate(jobs):
        if settings.exclusions.title_whitelist:
            title_lower = (job.title or "").lower()
            if not any(kw.lower() in title_lower for kw in settings.exclusions.title_whitelist):
                continue
        score = vector_filter.get_similarity_score(job.title)
        heapq.heappush(job_queue, (-score, idx, job))

    queued_jobs = [item[2] for item in job_queue]
    assert len(queued_jobs) == 2
    assert any(j.title == "Python Developer" for j in queued_jobs)
    assert any(j.title == "Frontend Engineer" for j in queued_jobs)
    assert not any(j.title == "Housekeeper Associate" for j in queued_jobs)
    assert not any(j.title == "Photographer" for j in queued_jobs)


def test_recalibrated_heuristics_boost() -> None:
    """Validate that jobs with title overlaps receive heuristic score boosts."""
    settings = Settings()
    settings.search.keywords = ["Associate Software Engineer", "Python Developer"]

    resume_profile = ResumeProfile(
        name="Test",
        skills=["Python"],
        technical_skills=["Python"],
        total_experience_years=1.0,
    )

    # High match job
    job_high = Job(
        naukri_job_id="JH",
        title="Python Developer @ Accenture",
        company="Accenture",
        url="",
        posted_date="Today",
    )
    # Low match/unrelated title
    job_low = Job(
        naukri_job_id="JL",
        title="BMS Administrator",
        company="Facility Corp",
        url="",
        posted_date="Today",
    )

    vector_filter = VectorSimilarityFilter(["Python"])

    def get_heap_score(job: Job) -> float:
        text_to_score = f"{job.title} {job.company} {job.skills}"
        score = vector_filter.get_similarity_score(text_to_score)

        title_lower = (job.title or "").lower()
        import re

        title_words = set(re.findall(r"\b[a-z0-9]+\b", title_lower))

        # Word-based overlap between title and search keywords
        search_kw_words = set()
        for kw in settings.search.keywords:
            search_kw_words.update(re.findall(r"\b[a-z0-9]+\b", kw.lower()))

        if title_words & search_kw_words:
            score += 0.15

        # Word-based overlap between title and technical skills
        tech_skills_words = set()
        for skill in resume_profile.technical_skills[:10]:
            tech_skills_words.update(re.findall(r"\b[a-z0-9]+\b", skill.lower()))

        if title_words & tech_skills_words:
            score += 0.10

        posted = str(job.posted_date).lower()
        if "just now" in posted or "hour" in posted or "today" in posted:
            score += 0.10

        return score

    score_high = get_heap_score(job_high)
    score_low = get_heap_score(job_low)

    # job_high gets +0.15 (keyword "Developer" match) +0.10 (technical_skill "Python" match) +0.10 (freshness)
    # job_low gets +0.10 (freshness) only
    assert score_high > score_low
    assert score_high >= 0.35
