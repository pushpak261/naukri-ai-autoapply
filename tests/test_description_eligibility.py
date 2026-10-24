"""A zero-year card must not override explicit mandatory experience in its body."""

from unittest.mock import AsyncMock

import pytest

from libs.common.agent_reasoning import description_experience_minimum, eligibility_concern
from src.naukri_agent.models.entities import Job, ResumeProfile


@pytest.mark.parametrize(
    "description,minimum",
    [
        (
            "Requirements: Product engineering experience, with 5+ years owning solution architecture.",
            5,
        ),
        (
            "Requirements: Extensive software experience, ideally 5+ years in architecture ownership.",
            None,
        ),
        (
            "Requirements Extensive experience in product engineering, including 5+ years guiding architecture. Nice to have Java.",
            5,
        ),
        ("Requirements: 3-5 years of relevant experience. Benefits: insurance.", 3),
        ("Minimum qualifications: 18 months of professional experience.", 1.5),
        ("Your expertise: 5+ years of experience in backend development.", 5),
        ("We require at least 4 years of industry experience.", 4),
        ("Minimum 2 years of work experience.", 2),
        ("Requirements: Java. Nice to have: 5 years of experience.", None),
        ("Requirements: Java. Preferred qualifications: 5 years of experience.", None),
        ("Requirements: Ideally 5 years of experience.", None),
        ("Requirements: 5 years of experience is preferred.", None),
        ("Our company was founded 30 years ago. Requirements: Java.", None),
        ("Requirements: Support a project lasting 5 years in production.", None),
        ("Responsibilities: Build applications over the next 5 years.", None),
        ("Requirements: Java. Benefits: 5 years of industry experience at our company.", None),
    ],
)
def test_required_description_tenure(description, minimum):
    assert description_experience_minimum(description) == minimum


def test_description_minimum_is_not_hidden_by_zero_year_card():
    job = Job(
        "example",
        "Solution Architect",
        "Employer",
        "https://example.invalid",
        experience="0 Yrs",
        description="Requirements: Extensive software experience, including 5+ years guiding architecture.",
    )
    assert "at least 5" in eligibility_concern(ResumeProfile(total_experience_years=1), job)
    assert eligibility_concern(ResumeProfile(total_experience_years=6), job) == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["naukri", "linkedin"])
@pytest.mark.parametrize("use_gemini", [True, False])
async def test_description_veto_precedes_model_and_match_cache(tmp_path, platform, use_gemini):
    if platform == "linkedin":
        from src.linked_agent.ai.job_matcher import LinkedInJobMatcher as Matcher
        from src.linked_agent.config.settings import Settings
        from src.linked_agent.models.entities import Job as Listing, ResumeProfile as Candidate
    else:
        from src.naukri_agent.ai.job_matcher import JobMatcher as Matcher
        from src.naukri_agent.config.settings import Settings

        Listing, Candidate = Job, ResumeProfile

    provider = AsyncMock()
    matcher = Matcher(provider, Settings(project_root=tmp_path, ai={"use_gemini": use_gemini}))
    profile = Candidate(total_experience_years=1, file_hash="example-resume")
    job = Listing(
        "example",
        "Solution Architect",
        "Employer",
        "https://example.invalid",
        experience="0 Yrs",
        description="Requirements: 5+ years guiding architecture. Nice to have: Java.",
    )
    # A prior positive result must never bypass the current eligibility evidence.
    matcher._cache.get = lambda *_: {"score": 100, "match_score": 100, "should_apply": True}
    result = await matcher.match(profile, job)
    assert result.should_apply is False
    assert "at least 5" in result.match_reasoning
    provider.generate_content.assert_not_awaited()
