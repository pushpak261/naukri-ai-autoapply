"""
Tests for the question answerer module.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.ai.question_answerer import QuestionAnswerer


@pytest.fixture
def mock_settings(tmp_path):
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.ai.gemini_api_key = "test_key"
    settings.ai.model = "gemini-2.5-flash"
    settings.ai.temperature = 0.3
    settings.project_root = tmp_path

    settings.profile.current_ctc = "10 LPA"
    settings.profile.expected_ctc = "15 LPA"
    settings.profile.notice_period = "30 days"
    settings.profile.total_experience = "3 years"
    settings.profile.current_location = "Bangalore"
    return settings


@pytest.fixture
def sample_resume():
    """A sample resume profile."""
    return {
        "name": "Jane Developer",
        "skills": ["Python", "FastAPI"],
        "total_experience_years": 3,
        "current_title": "Software Engineer",
    }


class TestQuestionAnswerer:
    """Tests for the QuestionAnswerer class."""

    @pytest.mark.asyncio
    async def test_direct_answers_from_profile(self, mock_settings, sample_resume):
        """Should answer common questions directly using settings profile values."""
        mock_llm = AsyncMock()
        answerer = QuestionAnswerer(mock_llm, mock_settings, sample_resume)

        questions = [
            {"question": "What is your current CTC?", "type": "text", "index": 0},
            {"question": "Expected salary details?", "type": "text", "index": 1},
            {"question": "What is your total experience?", "type": "text", "index": 2},
        ]

        job_data = {"title": "Python Dev", "company": "Tech Corp"}
        answers = await answerer.answer_questions(questions, job_data)

        assert len(answers) == 3
        assert answers[0]["answer"] == "10 LPA"
        assert answers[1]["answer"] == "15 LPA"
        assert answers[2]["answer"] == "3 years"

        # Verify LLM was not called
        mock_llm.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_sorting_and_index_mapping(self, mock_settings, sample_resume):
        """Should correctly preserve question index order and sort compiled answers."""
        mock_llm = AsyncMock()
        # Mock LLM to return response for the single AI question
        ai_response = [
            {
                "question": "Why do you want to join us?",
                "answer": "I love Python and FastAPI.",
                "confidence": "high",
            }
        ]
        mock_llm.generate_content.return_value = json.dumps(ai_response)

        answerer = QuestionAnswerer(mock_llm, mock_settings, sample_resume)

        # Q0 is answered directly (Notice period), Q1 goes to AI, Q2 is answered directly (Location)
        questions = [
            {"question": "Your notice period?", "type": "text", "index": 0},
            {"question": "Why do you want to join us?", "type": "text", "index": 1},
            {"question": "Current location?", "type": "text", "index": 2},
        ]

        job_data = {"title": "Python Dev", "company": "Tech Corp"}
        answers = await answerer.answer_questions(questions, job_data)

        assert len(answers) == 3
        # Direct notice period answer should be index 0
        assert answers[0]["question"] == "Your notice period?"
        assert answers[0]["answer"] == "30 days"
        assert answers[0]["index"] == 0

        # AI response should be index 1 (correctly mapped and sorted)
        assert answers[1]["question"] == "Why do you want to join us?"
        assert answers[1]["answer"] == "I love Python and FastAPI."
        assert answers[1]["index"] == 1

        # Direct location answer should be index 2
        assert answers[2]["question"] == "Current location?"
        assert answers[2]["answer"] == "Bangalore"
        assert answers[2]["index"] == 2
