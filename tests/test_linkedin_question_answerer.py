"""
Unit tests for the LinkedIn Easy Apply question answerer.
"""

from unittest.mock import AsyncMock, MagicMock
import json
import pytest

from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
from src.linked_agent.models.entities import Job, ResumeProfile


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.ai.use_gemini = True
    settings.ai.gemini_api_key = "test_gemini_key"
    settings.profile.current_ctc = "500000"
    settings.profile.expected_ctc = "700000"
    settings.profile.notice_period = "30"
    settings.profile.total_experience = "3"
    settings.profile.current_location = "Pune"
    return settings


@pytest.fixture
def sample_resume():
    """A sample resume profile."""
    return ResumeProfile(
        name="Pushpak Pandharpatte",
        email="pushpak@gmail.com",
        phone="9921626877",
        current_title="Software Engineer",
        summary="Experienced Full-Stack Developer",
        skills=["Java", "Python", "Google Gemini API"],
        total_experience_years=3,
        education=[],
    )


def test_clean_and_validate_answer_numeric_experience(mock_settings, sample_resume):
    """Should clean and validate numeric experience answers correctly."""
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)
    
    # 1. Answer has a clean number
    q1 = {"question": "How many years of experience do you have with Python?", "field_type": "text"}
    ans1 = answerer._clean_and_validate_answer(q1, "I have 2.5 years of experience.")
    assert ans1 == "2.5"

    ans1_int = answerer._clean_and_validate_answer(q1, "3 years")
    assert ans1_int == "3"

    # 2. Answer has no numbers, should fallback to profile total experience
    ans2 = answerer._clean_and_validate_answer(q1, "I have experience with Python in my projects.")
    assert ans2 == "3"  # Fallback to total_experience_years (3) from profile


def test_clean_and_validate_answer_salary(mock_settings, sample_resume):
    """Should clean and validate numeric salary answers correctly."""
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)
    
    q_expected = {"question": "What is your expected CTC?", "field_type": "text"}
    assert answerer._clean_and_validate_answer(q_expected, "7,00,000 INR") == "700000"
    assert answerer._clean_and_validate_answer(q_expected, "My expected salary is 700000") == "700000"
    assert answerer._clean_and_validate_answer(q_expected, "Negotiable") == "700000"  # fallback

    q_current = {"question": "Current salary?", "field_type": "text"}
    assert answerer._clean_and_validate_answer(q_current, "500000") == "500000"
    assert answerer._clean_and_validate_answer(q_current, "Not specified") == "500000"  # fallback


def test_clean_and_validate_answer_notice_period(mock_settings, sample_resume):
    """Should clean and validate numeric notice period answers."""
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)
    
    q = {"question": "What is your notice period (in days)?", "field_type": "text"}
    assert answerer._clean_and_validate_answer(q, "30 days") == "30"
    assert answerer._clean_and_validate_answer(q, "Immediate") == "30"  # fallback


def test_clean_and_validate_answer_dropdown_radio(mock_settings, sample_resume):
    """Should validate choice answers against the available options list."""
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)
    
    q_radio = {
        "question": "Are you comfortable working in a remote setting?",
        "field_type": "radio",
        "options": ["Yes", "No"]
    }
    # Exact match case insensitive
    assert answerer._clean_and_validate_answer(q_radio, "yes") == "Yes"
    # Substring match
    assert answerer._clean_and_validate_answer(q_radio, "I am comfortable working remotely: Yes") == "Yes"
    # Fallback to defaults
    assert answerer._clean_and_validate_answer(q_radio, "Maybe") == "Yes"


@pytest.mark.asyncio
async def test_parse_response_alignment(mock_settings, sample_resume):
    """Should correctly map, align, and clean/validate LLM answers with input questions."""
    answerer = LinkedInQuestionAnswerer(AsyncMock(), mock_settings, sample_resume)
    
    questions = [
        {"question": "How many years of work experience do you have with Artificial Intelligence (AI)?", "field_type": "text"},
        {"question": "What is your expected CTC?", "field_type": "text"},
        {"question": "Are you comfortable working in EST Time zone?", "field_type": "radio", "options": ["Yes", "No"]}
    ]
    
    # LLM returns fewer answers and in a different format
    llm_raw_response = json.dumps([
        {
            "question": "expected ctc",
            "answer": "Expected CTC is 7,00,000 INR"
        },
        {
            "question": "How many years of work experience do you have with Artificial Intelligence (AI)?",
            "answer": "I have worked with the Gemini API and AI solutions for 2 years."
        }
        # EST timezone question is missing from LLM response
    ])
    
    aligned = answerer._parse_response(llm_raw_response, questions)
    
    assert len(aligned) == 3
    # Check that alignment & cleaning worked correctly
    assert aligned[0]["question"] == questions[0]["question"]
    assert aligned[0]["answer"] == "2"  # cleaned from "2 years"
    
    assert aligned[1]["question"] == questions[1]["question"]
    assert aligned[1]["answer"] == "700000"  # cleaned from "7,00,000 INR"
    
    assert aligned[2]["question"] == questions[2]["question"]
    assert aligned[2]["answer"] == "Yes"  # fallback default choice
