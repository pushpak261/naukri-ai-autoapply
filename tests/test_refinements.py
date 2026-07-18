"""
Tests for composite deduplication and recalibrated heuristics.
"""

from __future__ import annotations

from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile
from src.naukri_agent.utils.similarity import VectorSimilarityFilter


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


def test_freshness_filter_refinements() -> None:
    """Validate that JobFilter._passes_freshness_filter handles relative ages accurately."""
    from src.naukri_agent.utils.filters import JobFilter

    # Test under 7 days limit
    filter_7 = JobFilter(max_experience=5, max_freshness_days=7)

    # 3 days ago should pass
    assert filter_7._passes_freshness_filter("3 Days Ago") is True
    # 7 days ago should pass
    assert filter_7._passes_freshness_filter("7 days ago") is True
    # 1 week ago (which is 7 days) should pass
    assert filter_7._passes_freshness_filter("1 week ago") is True
    # Few hours ago (0 days) should pass
    assert filter_7._passes_freshness_filter("Few hours ago") is True
    # yesterday (1 day) should pass
    assert filter_7._passes_freshness_filter("yesterday") is True
    # a day ago (1 day) should pass
    assert filter_7._passes_freshness_filter("a day ago") is True
    # 2 weeks ago (14 days) should fail
    assert filter_7._passes_freshness_filter("2 weeks ago") is False
    # 30+ days ago should fail
    assert filter_7._passes_freshness_filter("30+ Days Ago") is False

    # Test under 15 days limit
    filter_15 = JobFilter(max_experience=5, max_freshness_days=15)
    # 1 week ago (7 days) should pass
    assert filter_15._passes_freshness_filter("1 week ago") is True
    # 2 weeks ago (14 days) should pass
    assert filter_15._passes_freshness_filter("2 weeks ago") is True
    # 3 weeks ago (21 days) should fail
    assert filter_15._passes_freshness_filter("3 weeks ago") is False
    # 1 month ago (30 days) should fail
    assert filter_15._passes_freshness_filter("1 month ago") is False

    # Test disabled freshness limit (0)
    filter_disabled = JobFilter(max_experience=5, max_freshness_days=0)
    assert filter_disabled._passes_freshness_filter("30+ Days Ago") is True
    assert filter_disabled._passes_freshness_filter("3 weeks ago") is True
