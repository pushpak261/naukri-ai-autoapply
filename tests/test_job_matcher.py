"""
Tests for the job matcher module.

Tests matching logic, score validation, and edge cases.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.ai.job_matcher import JobMatcher
from src.core.exceptions import LLMQuotaExceededError


@pytest.fixture
def mock_settings(tmp_path):
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.ai.gemini_api_key = "test_key"
    settings.ai.model = "gemini-2.5-flash"
    settings.ai.temperature = 0.3
    settings.application.match_score_threshold = 70
    # MatchCache writes to <project_root>/data/match_cache.json — use a real
    # temp directory so the cache layer behaves like it would in production.
    settings.project_root = tmp_path
    return settings


@pytest.fixture
def sample_resume():
    """A sample resume profile."""
    return {
        "name": "Jane Developer",
        "skills": ["Python", "FastAPI", "Django", "PostgreSQL", "Docker", "AWS"],
        "total_experience_years": 4,
        "current_title": "Backend Developer",
        "summary": "Backend developer with 4 years of experience.",
    }


@pytest.fixture
def high_match_job():
    """A job that should score high against the sample resume."""
    return {
        "title": "Python Backend Developer",
        "company": "Tech Startup",
        "location": "Bangalore",
        "experience": "3-5 years",
        "salary": "12-18 LPA",
        "description": "Looking for a Python developer with FastAPI and PostgreSQL experience.",
        "skills": "Python, FastAPI, PostgreSQL, Docker",
    }


@pytest.fixture
def low_match_job():
    """A job that should score low against the sample resume."""
    return {
        "title": "iOS Developer",
        "company": "Mobile Corp",
        "location": "Delhi",
        "experience": "5-8 years",
        "salary": "20-30 LPA",
        "description": "Senior iOS developer with Swift and Objective-C expertise.",
        "skills": "Swift, Objective-C, iOS, Xcode",
    }


@pytest.fixture
def sample_match_response():
    """A sample AI match response."""
    return {
        "score": 85,
        "should_apply": True,
        "matching_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "missing_skills": [],
        "experience_fit": "strong",
        "location_fit": "match",
        "reasoning": "Strong backend match with relevant skills.",
        "strengths": ["Core skills match", "Experience level fits"],
        "concerns": [],
    }


class TestJobMatcher:
    """Tests for the JobMatcher class."""

    def test_matcher_creation(self, mock_settings):
        """Test that matcher can be created with an LLM provider and settings."""
        mock_llm = AsyncMock()
        matcher = JobMatcher(mock_llm, mock_settings)
        assert matcher is not None
        assert matcher._threshold == 70

    @pytest.mark.asyncio
    async def test_match_calls_llm_and_applies_threshold(
        self, mock_settings, sample_resume, high_match_job, sample_match_response
    ):
        """match() should call the LLM provider and respect the score threshold."""
        mock_llm = AsyncMock()
        mock_llm.generate_content.return_value = json.dumps(sample_match_response)

        matcher = JobMatcher(mock_llm, mock_settings)
        result = await matcher.match(sample_resume, high_match_job)

        mock_llm.generate_content.assert_awaited_once()
        assert result["score"] == 85
        assert result["should_apply"] is True  # 85 >= threshold of 70

    @pytest.mark.asyncio
    async def test_match_below_threshold_should_not_apply(
        self, mock_settings, sample_resume, low_match_job
    ):
        """A score below the configured threshold must yield should_apply=False."""
        mock_llm = AsyncMock()
        mock_llm.generate_content.return_value = json.dumps(
            {"score": 35, "matching_skills": [], "missing_skills": ["Swift"]}
        )

        matcher = JobMatcher(mock_llm, mock_settings)
        result = await matcher.match(sample_resume, low_match_job)

        assert result["score"] == 35
        assert result["should_apply"] is False

    @pytest.mark.asyncio
    async def test_match_handles_malformed_json_gracefully(
        self, mock_settings, sample_resume, high_match_job
    ):
        """If the LLM returns invalid JSON, match() should degrade safely instead of raising."""
        mock_llm = AsyncMock()
        mock_llm.generate_content.return_value = "not valid json {{{"

        matcher = JobMatcher(mock_llm, mock_settings)
        result = await matcher.match(sample_resume, high_match_job)

        assert result["score"] == 0
        assert result["should_apply"] is False

    @pytest.mark.asyncio
    async def test_match_propagates_quota_exhaustion(
        self, mock_settings, sample_resume, high_match_job
    ):
        """
        Quota exhaustion must NOT be swallowed into a fake score-0 result —
        that would silently mark every remaining job as a non-match instead
        of signaling that AI evaluation has stopped working. The caller
        (the orchestrator's job loop) needs this to propagate so it can
        stop the run gracefully.
        """
        mock_llm = AsyncMock()
        mock_llm.generate_content.side_effect = LLMQuotaExceededError(
            "daily quota exhausted", is_daily_quota=True
        )

        matcher = JobMatcher(mock_llm, mock_settings)
        with pytest.raises(LLMQuotaExceededError) as exc_info:
            await matcher.match(sample_resume, high_match_job)
        assert exc_info.value.is_daily_quota is True

    def test_match_result_structure(self, sample_match_response):
        """Test that a valid match result has all required fields."""
        required_fields = [
            "score",
            "should_apply",
            "matching_skills",
            "missing_skills",
            "experience_fit",
            "reasoning",
        ]
        for field in required_fields:
            assert field in sample_match_response

    def test_score_range(self, sample_match_response):
        """Test that score is within valid range."""
        score = sample_match_response["score"]
        assert 0 <= score <= 100

    def test_should_apply_logic(self, sample_match_response):
        """Test that should_apply is consistent with score and threshold."""
        # Score 85 >= threshold 70, so should_apply should be True
        assert sample_match_response["should_apply"] is True

    def test_matching_skills_are_list(self, sample_match_response):
        """Test that matching_skills is a list."""
        assert isinstance(sample_match_response["matching_skills"], list)

    def test_missing_skills_are_list(self, sample_match_response):
        """Test that missing_skills is a list."""
        assert isinstance(sample_match_response["missing_skills"], list)
