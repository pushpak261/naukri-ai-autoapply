"""
Tests for the question answerer module.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.naukri_agent.ai.question_answerer import QuestionAnswerer
from src.naukri_agent.models.entities import Job, ResumeProfile


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
    return ResumeProfile(
        name="Jane Developer",
        skills=["Python", "FastAPI"],
        total_experience_years=3.0,
        current_title="Software Engineer",
    )


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

        job = Job(
            naukri_job_id="test_job_1",
            title="Python Dev",
            company="Tech Corp",
            url="https://example.com/1",
        )
        answers = await answerer.answer_questions(questions, job)

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

        job = Job(
            naukri_job_id="test_job_2",
            title="Python Dev",
            company="Tech Corp",
            url="https://example.com/2",
        )
        answers = await answerer.answer_questions(questions, job)

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

    @pytest.mark.asyncio
    async def test_raw_resume_text_passed_to_prompt(self, mock_settings, sample_resume):
        """Should include raw resume text in LLM prompt when available."""
        sample_resume.raw_text = "Expert in Flutter and Dart development for 4 years."
        mock_llm = AsyncMock()
        mock_llm.generate_content.return_value = json.dumps([
            {"question": "How many years of experience in Flutter?", "answer": "4 years", "confidence": "high"}
        ])

        answerer = QuestionAnswerer(mock_llm, mock_settings, sample_resume)
        questions = [
            {"id": "q_flutter", "question": "Describe your hands-on experience in Flutter technology", "type": "text", "index": 0}
        ]
        job = Job(
            naukri_job_id="test_job_3",
            title="Flutter Dev",
            company="App Corp",
            url="https://example.com/3",
        )
        answers = await answerer.answer_questions(questions, job)

        assert len(answers) == 1
        assert answers[0]["id"] == "q_flutter"
        assert answers[0]["answer"] == "4 years"

        # Verify LLM call contained raw resume text
        call_kwargs = mock_llm.generate_content.call_args.kwargs
        assert "FULL RESUME TEXT:" in call_kwargs["prompt"]
        assert "Expert in Flutter and Dart" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_ai_answer_preserves_question_id_and_text(self, mock_settings, sample_resume):
        """Should preserve exact question text and ID even if Gemini slightly rephrases question text in output."""
        mock_llm = AsyncMock()
        # Mock LLM returning a slightly rephrased question string
        ai_response = [
            {
                "question": "Why join us?",  # Rephrased by LLM
                "answer": "Great career opportunity.",
                "confidence": "high",
            }
        ]
        mock_llm.generate_content.return_value = json.dumps(ai_response)

        answerer = QuestionAnswerer(mock_llm, mock_settings, sample_resume)
        questions = [
            {
                "id": "agent_q_99",
                "question": "Why do you want to join our organization?",
                "type": "text",
                "index": 0,
            }
        ]
        job = Job(
            naukri_job_id="test_job_4",
            title="Software Engineer",
            company="Tech Corp",
            url="https://example.com/4",
        )
        answers = await answerer.answer_questions(questions, job)

        assert len(answers) == 1
        assert answers[0]["id"] == "agent_q_99"
        # Original question string must be preserved
        assert answers[0]["question"] == "Why do you want to join our organization?"
        assert answers[0]["answer"] == "Great career opportunity."

    @pytest.mark.asyncio
    async def test_skill_experience_question_not_hijacked_by_direct_answer(self, mock_settings, sample_resume):
        """Skill-specific questions like HTML/CSS experience should go to Gemini, not hijacked by direct total experience patterns."""
        mock_llm = AsyncMock()
        mock_llm.generate_content.return_value = json.dumps([
            {
                "id": "q_html",
                "question": "How many years of experience do you have in HTML?",
                "answer": "1",
                "confidence": "high",
            }
        ])

        answerer = QuestionAnswerer(mock_llm, mock_settings, sample_resume)
        questions = [
            {
                "id": "q_html",
                "question": "How many years of experience do you have in HTML?",
                "type": "text",
                "index": 0,
            }
        ]
        job = Job(
            naukri_job_id="test_job_5",
            title="Frontend Engineer",
            company="BMW TechWorks",
            url="https://example.com/5",
        )
        answers = await answerer.answer_questions(questions, job)

        assert len(answers) == 1
        assert answers[0]["answer"] == "1"
        # Verify LLM WAS called (not intercepted by direct answer pattern)
        mock_llm.generate_content.assert_called_once()

    def test_cache_validation_rejects_dom_element_ids(self, mock_settings):
        """QACache.set should reject element IDs, DOM selectors, and generic placeholders."""
        from src.naukri_agent.ai.question_answerer import QACache
        cache = QACache(mock_settings.project_root / "data" / "qa_cache.json")

        # Invalid keys should be ignored
        cache.set("userInput__rzxx3j402InputBox", "Pushpak Pandharpatte")
        cache.set("agent_chat_q", "Some Answer")
        cache.set("short", "Val")

        assert cache.get("userInput__rzxx3j402InputBox") is None
        assert cache.get("agent_chat_q") is None
        assert cache.get("short") is None

        # Valid question key should be accepted
        cache.set("How many years of experience do you have in React?", "2 years")
        assert cache.get("How many years of experience do you have in React?") == "2 years"


