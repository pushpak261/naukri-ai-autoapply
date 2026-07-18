"""
Unit tests for LinkedIn screening question answering positive bias and form filling logic.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
from src.linked_agent.models.entities import ResumeProfile


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = MagicMock()
    settings.ai.use_gemini = True
    settings.ai.gemini_api_key = "test_key"
    settings.profile.current_ctc = "500000"
    settings.profile.expected_ctc = "700000"
    settings.profile.notice_period = "0 days"
    settings.profile.total_experience = "3"
    return settings


@pytest.fixture
def sample_resume():
    """Sample candidate resume."""
    return ResumeProfile(
        name="Pushpak Pandharpatte",
        email="pushpak@gmail.com",
        phone="9921626877",
        current_title="Software Engineer",
        skills=["Java", "Python"],
        total_experience_years=3,
    )


def test_positive_answer_bias_for_comfortable_questions(mock_settings, sample_resume):
    """Verify that questions asking about comfort/willingness select 'Yes'."""
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)

    q1 = {
        "question": "Are you comfortable commuting to Bangalore?",
        "field_type": "radio",
        "options": ["Yes", "No"]
    }
    # Regardless of LLM raw string, validation should select "Yes"
    ans1 = answerer._clean_and_validate_answer(q1, "No")
    assert ans1 == "Yes"

    q2 = {
        "question": "Are you willing to work in EST shift?",
        "field_type": "radio",
        "options": ["Yes", "No"]
    }
    ans2 = answerer._clean_and_validate_answer(q2, "Unsure")
    assert ans2 == "Yes"


def test_notice_period_zero_cleaning(mock_settings, sample_resume):
    """Verify that notice period questions return clean integer string '0' when notice period is 0/immediate."""
    mock_settings.profile.notice_period = "0"
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)

    q_np = {"question": "What is your official Notice Period?*", "field_type": "text"}
    
    # 1. Clean from "0 days"
    assert answerer._clean_and_validate_answer(q_np, "0 days") == "0"
    # 2. Clean from "0"
    assert answerer._clean_and_validate_answer(q_np, "0") == "0"
    # 3. Clean from "Immediate" fallback
    assert answerer._clean_and_validate_answer(q_np, "Immediate") == "0"
