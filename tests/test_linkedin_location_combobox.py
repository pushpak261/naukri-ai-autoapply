"""
Unit tests for Location (city) combobox answer formatting and cleaning.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
from src.linked_agent.models.entities import ResumeProfile


@pytest.fixture
def mock_settings():
    """Mock settings with location Pune."""
    settings = MagicMock()
    settings.ai.use_gemini = True
    settings.ai.gemini_api_key = "test_key"
    settings.profile.current_location = "Pune"
    return settings


@pytest.fixture
def sample_resume():
    """Sample resume profile."""
    return ResumeProfile(
        name="Pushpak Pandharpatte",
        email="pushpak@gmail.com",
        phone="9921626877",
        current_title="Software Engineer",
        skills=["Python"],
        total_experience_years=3,
    )


def test_location_question_answering(mock_settings, sample_resume):
    """Verify that location questions are formatted as 'Pune Division, Maharashtra, India'."""
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)

    q = {"question": "Location (city)*", "field_type": "text"}
    cleaned_ans = answerer._clean_and_validate_answer(q, "Pune")
    assert cleaned_ans == "Pune Division, Maharashtra, India"

    q2 = {"question": "City", "field_type": "text"}
    cleaned_ans2 = answerer._clean_and_validate_answer(q2, "")
    assert cleaned_ans2 == "Pune Division, Maharashtra, India"
