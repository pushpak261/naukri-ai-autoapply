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
        assert answers[2]["answer"] == "1 year"

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
    async def test_skill_experience_question_hijacked_by_direct_answer(self, mock_settings, sample_resume):
        """Skill-specific questions like HTML/CSS experience should be hijacked by direct total experience patterns and answered directly."""
        mock_llm = AsyncMock()
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
        # Verify LLM was NOT called
        mock_llm.generate_content.assert_not_called()

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


# ---------------------------------------------------------------------------
# Extended coverage for src/naukri_agent/ai/question_answerer.py
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
import builtins  # noqa: E402
import io  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from src.naukri_agent.ai.question_answerer import (  # noqa: E402
    DIRECT_ANSWER_PATTERNS,
    QACache,
    ScreeningAnswer,
    _normalize_question_text,
)
from src.naukri_agent.utils.exceptions import (  # noqa: E402
    LLMAPIError,
    LLMQuotaExceededError,
)
from tests.test_question_answerer_helpers import (  # noqa: E402
    ai_reply,
    make_answerer,
    make_job,
    make_llm,
    make_profile,
    make_settings,
    q,
    today_ddmmyyyy,
)

UNANSWERABLE = "Favourite colour of the sky"
EMPTY_LOW = {"id": "q1", "question": "Favourite colour", "answer": "", "confidence": "low"}


class _FakeTTY(io.StringIO):
    """A stdin double that claims to be an interactive terminal."""

    def isatty(self) -> bool:
        return True


class TestNormalizeQuestionText:
    """Tests for the question-text normalizer."""

    def test_lowercases_collapses_whitespace_and_strips_punctuation(self):
        assert _normalize_question_text("  What   is  your\tName?? ") == "what is your name"

    def test_drops_non_ascii_symbols_to_spaces(self):
        assert _normalize_question_text("Expected CTC (in LPA)!") == "expected ctc in lpa"

    def test_empty_and_none_like_inputs_normalise_to_empty_string(self):
        assert _normalize_question_text("") == ""
        assert _normalize_question_text("!!!") == ""
        assert _normalize_question_text(None) == ""


class TestQACachePersistence:
    """Disk behaviour of :class:`QACache`."""

    def test_existing_valid_cache_file_is_loaded_on_construction(self, tmp_path):
        cache_file = tmp_path / "data" / "qa_cache.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps({"notice period": "Immediate", "favourite hobby": "Chess"}),
            encoding="utf-8",
        )

        cache = QACache(cache_file)

        assert cache.get("notice period") == "Immediate"
        assert cache.get("favourite hobby") == "Chess"

    def test_corrupt_cache_file_degrades_to_empty_cache(self, tmp_path):
        cache_file = tmp_path / "data" / "qa_cache.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("{ this is not json", encoding="utf-8")

        cache = QACache(cache_file)

        assert cache.get("notice period") is None
        assert cache.get("favourite hobby") is None

    def test_missing_cache_file_starts_empty(self, tmp_path):
        cache = QACache(tmp_path / "data" / "qa_cache.json")

        assert cache.get("notice period") is None
        assert not (tmp_path / "data" / "qa_cache.json").exists()

    def test_save_writes_indented_utf8_json_and_creates_parent_dirs(self, tmp_path):
        cache_file = tmp_path / "nested" / "deeper" / "qa_cache.json"
        cache = QACache(cache_file)
        cache.set("What is your notice period?", "Immediate")
        cache.save()

        assert cache_file.exists()
        assert json.loads(cache_file.read_text(encoding="utf-8")) == {
            "what is your notice period": "Immediate"
        }
        assert "\n  " in cache_file.read_text(encoding="utf-8")

    def test_save_failure_is_swallowed_when_parent_is_a_file(self, tmp_path):
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        cache = QACache(blocker / "qa_cache.json")
        cache.set("What is your notice period?", "Immediate")

        cache.save()

        assert blocker.is_file()
        assert not (blocker / "qa_cache.json").exists()

    def test_reload_round_trips_entries_written_by_another_instance(self, tmp_path):
        cache_file = tmp_path / "data" / "qa_cache.json"
        writer = QACache(cache_file)
        writer.set("Preferred work location?", "Bangalore, Pune")
        writer.save()

        reader = QACache(cache_file)

        assert reader.get("Preferred work location?") == "Bangalore, Pune"


class TestQACacheLookup:
    """Key matching and validation rules of :class:`QACache`."""

    def test_empty_normalised_key_returns_none(self, tmp_path):
        cache = QACache(tmp_path / "qa_cache.json")
        cache._qa_cache = {"": "ignored"}

        assert cache.get("") is None
        assert cache.get("??!!") is None

    def test_unnormalised_raw_key_hit_does_not_need_fuzzy_match(self, tmp_path, monkeypatch):
        cache = QACache(tmp_path / "qa_cache.json")
        cache._qa_cache = {"  What Is Your Name  ": "Jane Developer"}
        monkeypatch.setattr(
            "src.naukri_agent.utils.fuzzy.fuzzy_similarity_ratio", lambda *_args: 0.0
        )

        assert cache.get("  What Is Your Name  ") == "Jane Developer"

    def test_typo_in_question_hits_cached_answer_via_fuzzy_match(self, tmp_path):
        cache = QACache(tmp_path / "qa_cache.json")
        cache._qa_cache = {
            "zzzzzzzzzzzzzzzzzzzzzz": "Worst match",
            "how many years of experience": "5 years",
        }

        assert cache.get("how many years of experiance") == "5 years"

    def test_unrelated_question_does_not_fuzzy_match(self, tmp_path):
        cache = QACache(tmp_path / "qa_cache.json")
        cache.set("How many years of experience do you have?", "5 years")

        assert cache.get("What is your favourite cuisine") is None

    def test_set_rejects_agent_and_question_placeholder_keys(self, tmp_path):
        cache = QACache(tmp_path / "qa_cache.json")

        cache.set("agent chat question about notice", "Immediate")
        cache.set("select the notice period option", "Immediate")
        cache.set("Question 1 please answer", "Immediate")
        cache.set("option notice period", "Immediate")

        assert cache.get("agent chat question about notice") is None
        assert cache.get("select the notice period option") is None
        assert cache.get("Question 1 please answer") is None
        assert cache.get("option notice period") is None

    def test_set_rejects_dom_element_identifiers_with_underscores(self, tmp_path):
        cache = QACache(tmp_path / "qa_cache.json")

        cache.set("agent_chat_value", "Jane")
        cache.set("select_notice", "Jane")
        cache.set("option_notice", "Jane")

        assert cache.get("agent_chat_value") is None
        assert cache.get("select_notice") is None
        assert cache.get("option_notice") is None

    @pytest.mark.parametrize("answer", ["", "   ", None])
    def test_set_ignores_blank_answers(self, tmp_path, answer):
        cache = QACache(tmp_path / "qa_cache.json")

        cache.set("What is your notice period?", answer)

        assert cache.get("What is your notice period?") is None

    def test_set_ignores_keys_shorter_than_six_characters(self, tmp_path):
        cache = QACache(tmp_path / "qa_cache.json")

        cache.set("DOB?", "01/01/1998")

        assert cache.get("DOB?") is None

    def test_set_stores_under_normalised_key_and_is_case_insensitive(self, tmp_path):
        cache = QACache(tmp_path / "qa_cache.json")

        cache.set("What   is YOUR notice period?", "Immediate")

        assert cache.get("what is your notice period?") == "Immediate"
        assert cache.get("WHAT IS YOUR NOTICE PERIOD") == "Immediate"


class TestTryDirectAnswerFuzzyAndTable:
    """Trie, fuzzy and lookup-table behaviour of ``_try_direct_answer``."""

    def test_fuzzy_typo_still_resolves_via_pattern_table(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._try_direct_answer("notice perod", "text") == "30 days"

    def test_unknown_question_returns_none(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._try_direct_answer("favourite colour of the sky", "text") is None

    def test_empty_question_returns_none(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._try_direct_answer("", "text") is None

    def test_resolved_key_with_blank_value_returns_none(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.profile.date_of_birth = ""
        settings.profile.marital_status = ""
        answerer = make_answerer(tmp_path, settings=settings, profile=make_profile(email="", phone=""))
        settings.naukri.email = ""
        settings.naukri.mobile_number = ""

        assert answerer._try_direct_answer("email id", "text") is None
        assert answerer._try_direct_answer("date of birth", "text") is None

    def test_experience_questions_always_report_one_year(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._try_direct_answer("What is your total experience?", "text") == "1 year"
        assert answerer._try_direct_answer("How many months of exp do you have?", "text") == "1 year"

    def test_descriptive_skill_questions_are_deferred_to_the_llm(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._try_direct_answer("Describe your React projects", "text") is None

    def test_total_experience_phrase_bypasses_the_skill_safeguard(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert (
            answerer._try_direct_answer("What is your total experience in Java?", "text") == "1 year"
        )

    def test_number_fields_get_bare_digits(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._try_direct_answer("current ctc", "number", None) == "10"
        assert answerer._try_direct_answer("Enter digits of your notice period", "text", None) == "30"

    def test_choice_field_exact_option_match(self, tmp_path):
        answerer = make_answerer(tmp_path)

        answer = answerer._try_direct_answer(
            "What is your current CTC?", "dropdown", [{"text": " 10 LPA "}, {"text": "12 LPA"}]
        )

        assert answer == " 10 LPA "

    @pytest.mark.parametrize(
        "options",
        [
            [{"text": "0-8 LPA"}, {"text": "8-12 LPA"}],
            [{"text": "5 LPA or more"}],
            [{"text": "below 15 LPA"}],
            [{"text": "10"}],
        ],
        ids=["range", "at-least", "at-most", "equal"],
    )
    def test_choice_field_numeric_matching(self, tmp_path, options):
        answerer = make_answerer(tmp_path)

        assert answerer._try_direct_answer("current ctc", "radio", options) == options[-1]["text"]

    def test_choice_field_substring_match(self, tmp_path):
        answerer = make_answerer(tmp_path)

        answer = answerer._try_direct_answer(
            "current location", "dropdown", [{"text": "Work from Bangalore office"}]
        )
        assert answer == "Work from Bangalore office"

        answer = answerer._try_direct_answer(
            "preferred work location", "radio", [{"text": "Bangalore"}, {"text": "Mumbai"}]
        )
        assert answer == "Bangalore"

    def test_choice_field_relocation_fallback(self, tmp_path):
        answerer = make_answerer(tmp_path)

        answer = answerer._try_direct_answer(
            "are you willing to relocate?", "dropdown", [{"text": "willing to relocate"}]
        )

        assert answer == "willing to relocate"

    def test_choice_field_relocation_agree_fallback(self, tmp_path):
        answerer = make_answerer(tmp_path)

        answer = answerer._try_direct_answer(
            "are you willing to relocate?", "checkbox", [{"text": "I agree to relocate"}]
        )

        assert answer == "I agree to relocate"

    def test_choice_field_notice_period_immediate_fallback(self, tmp_path):
        answerer = make_answerer(tmp_path)

        answer = answerer._try_direct_answer(
            "notice period", "dropdown", [{"text": "2 months"}, {"text": "Immediately"}]
        )

        assert answer == "Immediately"

    def test_choice_field_without_any_match_defers_to_the_llm(self, tmp_path):
        answerer = make_answerer(tmp_path)

        answer = answerer._try_direct_answer(
            "notice period", "dropdown", [{"text": "2 months"}, {"text": "3 months"}]
        )

        assert answer is None


class TestDirectAnswerLookupTable:
    """``_direct_answers`` construction in ``__init__``."""

    def test_settings_and_profile_values_win(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._direct_answers["current_ctc"] == "10 LPA"
        assert answerer._direct_answers["expected_ctc"] == "15 LPA"
        assert answerer._direct_answers["notice_period"] == "30 days"
        assert answerer._direct_answers["current_location"] == "Bangalore"
        assert answerer._direct_answers["preferred_location"] == "Bangalore, Pune"
        assert answerer._direct_answers["languages"] == "English, Hindi"
        assert answerer._direct_answers["candidate_name"] == "Jane Developer"
        assert answerer._direct_answers["reloc_consent"] == "Yes"
        assert answerer._direct_answers["graduation_year"] == "2023"
        assert answerer._direct_answers["qualification"].startswith("PG-DAC")

    def test_hardcoded_defaults_when_settings_and_profile_are_empty(self, tmp_path):
        answerer = make_answerer(
            tmp_path,
            settings=make_settings(
                tmp_path,
                current_ctc="",
                expected_ctc="",
                notice_period="",
                total_experience="",
                current_location="",
                preferred_locations=[],
                languages=[],
                github_url="",
                linkedin_url="",
                date_of_birth="",
                marital_status="",
            ),
            profile=make_profile(
                name="", email="", phone="", current_title="", total_experience_years=0.0
            ),
        )

        direct = answerer._direct_answers
        assert direct["current_ctc"] == "4.5 LPA"
        assert direct["expected_ctc"] == "6 LPA"
        assert direct["notice_period"] == "Immediate"
        assert direct["total_experience"] == "1 years"
        assert direct["current_location"] == "Pune"
        assert direct["preferred_location"] == "Pune"
        assert direct["candidate_name"] == "Candidate"
        assert direct["candidate_email"] == ""
        assert direct["candidate_phone"] == ""
        assert direct["date_of_birth"] == ""
        assert direct["marital_status"] == ""
        assert direct["languages"] == "English, Hindi, Marathi"

    def test_total_experience_falls_back_to_resume_years(self, tmp_path):
        settings = make_settings(tmp_path, total_experience="")

        answerer = make_answerer(
            tmp_path, settings=settings, profile=make_profile(total_experience_years=4.0)
        )

        assert answerer._direct_answers["total_experience"] == "4.0 years"

    def test_current_location_falls_back_to_resume_title_then_hardcoded(self, tmp_path):
        settings = make_settings(tmp_path, current_location="")

        titled = make_answerer(
            tmp_path, settings=settings, profile=make_profile(current_title="Software Engineer")
        )
        untitled = make_answerer(
            tmp_path, settings=settings, profile=make_profile(current_title="")
        )

        assert titled._direct_answers["current_location"] == "Software Engineer"
        assert untitled._direct_answers["current_location"] == "Pune"

    def test_contacts_fall_back_to_naukri_credentials(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.naukri.email = "naukri-login@example.com"
        settings.naukri.mobile_number = "9000000000"

        answerer = make_answerer(
            tmp_path, settings=settings, profile=make_profile(email="", phone="")
        )

        assert answerer._direct_answers["candidate_email"] == "naukri-login@example.com"
        assert answerer._direct_answers["candidate_phone"] == "9000000000"

    def test_every_pattern_maps_to_a_known_answer_key(self, tmp_path):
        answerer = make_answerer(tmp_path)

        missing = {
            key
            for key in DIRECT_ANSWER_PATTERNS.values()
            if key not in answerer._direct_answers
        }

        assert missing == set()

    def test_cache_file_lives_under_the_project_root(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._cache._cache_file == tmp_path / "data" / "qa_cache.json"


class TestAnswerQuestionsFlow:
    """End-to-end orchestration of ``answer_questions``."""

    @pytest.mark.asyncio
    async def test_no_questions_returns_empty_list(self, tmp_path):
        llm = make_llm()
        answerer = make_answerer(tmp_path, llm=llm)

        assert await answerer.answer_questions([], make_job()) == []
        llm.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_direct_answers_win_over_the_llm(self, tmp_path):
        llm = make_llm()
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer.answer_questions(
            [
                q("What is your current CTC?", id="c1", index=0),
                q("Your notice period?", index=1),
                {"question": "Preferred work location?"},
            ],
            make_job(),
        )

        assert [entry["answer"] for entry in answers] == ["10 LPA", "30 days", "Bangalore, Pune"]
        assert [entry["confidence"] for entry in answers] == ["high", "high", "high"]
        assert answers[0]["id"] == "c1"
        llm.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_answers_without_calling_the_llm(self, tmp_path):
        llm = make_llm()
        answerer = make_answerer(tmp_path, llm=llm)
        answerer._cache.set("Favourite colour of the sky", "Blue")
        answerer._cache.save()

        reloaded = make_answerer(tmp_path, llm=llm)

        answers = await reloaded.answer_questions(
            [q("Favourite colour of the sky", id="c1", index=0)], make_job()
        )

        assert answers == [
            {
                "id": "c1",
                "question": "Favourite colour of the sky",
                "answer": "Blue",
                "confidence": "high",
                "index": 0,
            }
        ]
        llm.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_gemini_yields_blank_low_confidence_answers(self, tmp_path):
        llm = make_llm()
        settings = make_settings(tmp_path)
        settings.ai.use_gemini = False
        answerer = make_answerer(tmp_path, settings=settings, llm=llm)

        answers = await answerer.answer_questions(
            [q(UNANSWERABLE, id="c1", index=0)], make_job()
        )

        assert answers[0]["answer"] == ""
        assert answers[0]["confidence"] == "low"
        assert answers[0]["id"] == "c1"
        llm.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_pdf_mode_yields_blank_low_confidence_answers(self, tmp_path):
        llm = make_llm()
        settings = make_settings(tmp_path)
        settings.application.answer_questions_with_pdf = False
        answerer = make_answerer(tmp_path, settings=settings, llm=llm)

        answers = await answerer.answer_questions(
            [q(UNANSWERABLE, id="c1", index=0)], make_job()
        )

        assert answers[0]["answer"] == ""
        assert answers[0]["confidence"] == "low"
        llm.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_blank_ai_answer_is_replaced_by_intelligent_fallback(self, tmp_path, monkeypatch):
        llm = make_llm(ai_reply({"id": "q1", "question": "Rate your proficiency in Excel", "answer": "  "}))
        answerer = make_answerer(tmp_path, llm=llm)
        monkeypatch.setattr(sys, "stdin", io.StringIO())

        answers = await answerer.answer_questions(
            [q("Rate your proficiency in Excel", id="q1", index=0)], make_job()
        )

        assert answers[0]["answer"] == "8"
        assert answers[0]["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_direct_cache_and_ai_answers_are_merged_and_sorted(self, tmp_path):
        llm = make_llm(ai_reply({"question": "Favourite season", "answer": "Autumn", "confidence": "high"}))
        answerer = make_answerer(tmp_path, llm=llm)
        answerer._cache.set("Favourite colour of the sky", "Blue")

        answers = await answerer.answer_questions(
            [
                q("Favourite colour of the sky", index=2),
                q("Favourite season", index=0),
                q("current ctc", index=1),
            ],
            make_job(),
        )

        assert [(entry["question"], entry["answer"]) for entry in answers] == [
            ("Favourite season", "Autumn"),
            ("current ctc", "10 LPA"),
            ("Favourite colour of the sky", "Blue"),
        ]

    @pytest.mark.asyncio
    async def test_direct_answers_without_index_fall_back_to_result_position(self, tmp_path):
        answerer = make_answerer(tmp_path, llm=make_llm())

        answers = await answerer.answer_questions(
            [{"question": "current ctc", "type": "text"}, {"question": "notice period", "type": "text"}],
            make_job(),
        )

        assert [(entry["question"], entry["index"]) for entry in answers] == [
            ("current ctc", 0),
            ("notice period", 1),
        ]

    @pytest.mark.asyncio
    async def test_ai_answers_without_index_default_to_zero_and_merge_last(self, tmp_path):
        llm = make_llm(ai_reply({"question": UNANSWERABLE, "answer": "Blue", "confidence": "high"}))
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer.answer_questions(
            [{"question": UNANSWERABLE, "type": "text"}, {"question": "current ctc", "type": "text"}],
            make_job(),
        )

        assert [(entry["question"], entry["index"], entry["id"]) for entry in answers] == [
            ("current ctc", 0, None),
            (UNANSWERABLE, 0, None),
        ]


class TestInteractiveClarification:
    """The ``input()`` prompt path inside ``answer_questions``."""

    @pytest.mark.asyncio
    async def test_user_answer_is_stripped_promoted_and_cached(self, tmp_path, monkeypatch):
        llm = make_llm(ai_reply(EMPTY_LOW))
        answerer = make_answerer(tmp_path, llm=llm)
        monkeypatch.setattr(sys, "stdin", _FakeTTY())
        prompts: list[str] = []

        def fake_input(prompt=""):
            prompts.append(prompt)
            return "  Indigo  "

        monkeypatch.setattr(builtins, "input", fake_input)

        answers = await answerer.answer_questions(
            [
                q(
                    "Favourite colour",
                    id="q1",
                    type="dropdown",
                    options=[{"text": "Red"}, {"text": "Blue"}],
                    index=0,
                )
            ],
            make_job(),
        )

        assert prompts == ["   Enter answer: "]
        assert answers[0]["answer"] == "Indigo"
        assert answers[0]["confidence"] == "high"
        assert json.loads((tmp_path / "data" / "qa_cache.json").read_text(encoding="utf-8")) == {
            "favourite colour": "Indigo"
        }

    @pytest.mark.asyncio
    async def test_input_runs_off_the_event_loop_thread(self, tmp_path, monkeypatch):
        llm = make_llm(ai_reply(EMPTY_LOW))
        answerer = make_answerer(tmp_path, llm=llm)
        monkeypatch.setattr(sys, "stdin", _FakeTTY())
        threads: list[threading.Thread] = []
        loop_progress: list[bool] = []

        heartbeat_fired = asyncio.Event()

        async def heartbeat():
            await asyncio.sleep(0.01)
            heartbeat_fired.set()

        def fake_input(prompt=""):
            threads.append(threading.current_thread())
            time.sleep(0.15)
            loop_progress.append(heartbeat_fired.is_set())
            return "Indigo"

        monkeypatch.setattr(builtins, "input", fake_input)
        beat = asyncio.create_task(heartbeat())

        answers = await answerer.answer_questions(
            [q("Favourite colour", id="q1", index=0)], make_job()
        )
        await beat

        assert answers[0]["answer"] == "Indigo"
        assert threads and threads[0] is not threading.main_thread()
        assert loop_progress == [True]

    @pytest.mark.asyncio
    async def test_blank_user_answer_leaves_the_fallback_in_place(self, tmp_path, monkeypatch):
        llm = make_llm(ai_reply(EMPTY_LOW))
        answerer = make_answerer(tmp_path, llm=llm)
        monkeypatch.setattr(sys, "stdin", _FakeTTY())
        monkeypatch.setattr(builtins, "input", lambda prompt="": "   ")

        answers = await answerer.answer_questions(
            [q("Favourite colour", id="q1", index=0)], make_job()
        )

        assert answers[0]["answer"] == "Yes"
        assert answers[0]["confidence"] == "medium"
        assert not (tmp_path / "data" / "qa_cache.json").exists()

    @pytest.mark.asyncio
    async def test_input_failure_is_swallowed_and_fallback_used(self, tmp_path, monkeypatch):
        llm = make_llm(ai_reply(EMPTY_LOW))
        answerer = make_answerer(tmp_path, llm=llm)
        monkeypatch.setattr(sys, "stdin", _FakeTTY())

        def exploding_input(prompt=""):
            raise EOFError("no terminal available")

        monkeypatch.setattr(builtins, "input", exploding_input)

        answers = await answerer.answer_questions(
            [q("Favourite colour", id="q1", index=0)], make_job()
        )

        assert answers[0]["answer"] == "Yes"
        assert answers[0]["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_prompt_is_skipped_when_stdin_is_not_a_tty(self, tmp_path, monkeypatch):
        llm = make_llm(ai_reply(EMPTY_LOW))
        answerer = make_answerer(tmp_path, llm=llm)
        monkeypatch.setattr(sys, "stdin", io.StringIO())
        monkeypatch.setattr(
            builtins, "input", MagicMock(side_effect=AssertionError("must not prompt"))
        )

        answers = await answerer.answer_questions(
            [q("Favourite colour", id="q1", index=0)], make_job()
        )

        assert answers[0]["answer"] == "Yes"
        assert answers[0]["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_confident_ai_answers_are_not_prompted(self, tmp_path, monkeypatch):
        llm = make_llm(ai_reply({"id": "q1", "question": "Favourite colour", "answer": "Blue", "confidence": "high"}))
        answerer = make_answerer(tmp_path, llm=llm)
        monkeypatch.setattr(sys, "stdin", _FakeTTY())
        monkeypatch.setattr(
            builtins, "input", MagicMock(side_effect=AssertionError("must not prompt"))
        )

        answers = await answerer.answer_questions(
            [q("Favourite colour", id="q1", index=0)], make_job()
        )

        assert answers[0]["answer"] == "Blue"
        assert answers[0]["confidence"] == "high"


class TestIntelligentFallback:
    """``_generate_intelligent_fallback`` keyword routing."""

    @pytest.mark.parametrize(
        ("entry", "expected"),
        [
            ({"question": "total experience"}, "1 year"),
            ({"question": "total experience", "type": "number"}, "1"),
            ({"question": "how many years of exp"}, "1 year"),
            ({"question": "current ctc"}, "10 LPA"),
            ({"question": "desired salary"}, "10 LPA"),
            ({"question": "current package compensation"}, "10 LPA"),
            ({"question": "notice period"}, "30 days"),
            ({"question": "earliest joining date"}, "30 days"),
            ({"question": "preferred work location"}, "Bangalore, Pune"),
            ({"question": "your current city"}, "Bangalore"),
            ({"question": "willing to travel for this role"}, "Yes"),
            ({"question": "comfortable with night shift"}, "Yes"),
            ({"question": "do you agree to the terms"}, "Yes"),
            ({"question": "do you authorize the background check"}, "Yes"),
            ({"question": "highest qualification"}, "PG-DAC / Bachelor of Mechanical Engineering"),
            ({"question": "your degree"}, "PG-DAC / Bachelor of Mechanical Engineering"),
            ({"question": "graduation year"}, "2023"),
            ({"question": "passing year"}, "2023"),
            ({"question": "gender"}, "Male"),
            ({"question": "full name"}, "Jane Developer"),
            ({"question": "email address"}, "jane@example.com"),
            ({"question": "phone number"}, "9998887776"),
            ({"question": "contact number"}, "9998887776"),
            ({"question": "date of birth"}, "01/01/1998"),
            ({"question": "marital status"}, "Single"),
            ({"question": "language proficiency"}, "Fluent"),
            ({"question": "share your github profile"}, "https://github.com/tester"),
            ({"question": "rate your skill proficiency"}, "Advanced"),
            ({"question": "how would you rate yourself"}, "8"),
            (
                {"question": "your strength"},
                "Strong problem-solving skills and ability to deliver high-quality code",
            ),
            (
                {"question": "your weakness"},
                "I focus heavily on code quality and sometimes need to balance speed with perfection",
            ),
            ({"question": "reason for change"}, "Looking for a product company"),
            (
                {"question": "why should we hire you"},
                "1 year of hands-on experience building scalable Java Developer solutions "
                "with modern tech stack",
            ),
            (
                {"question": "describe your project"},
                "Developed full-stack web applications and microservices using Spring Boot, "
                "React, and MySQL with CI/CD",
            ),
            ({"question": "your availability to start"}, "Immediate"),
            ({"question": "share your website link"}, "https://linkedin.com/in/tester"),
            (
                {"question": "select the option", "type": "dropdown", "options": [{"text": "Alpha"}]},
                "Alpha",
            ),
            ({"question": "zzzz qqqq"}, "Yes"),
            ({"question": ""}, "Yes"),
        ],
    )
    def test_fallback_answer_for_question(self, tmp_path, entry, expected):
        answerer = make_answerer(tmp_path)

        assert answerer._generate_intelligent_fallback(entry, make_job()) == expected

    def test_date_questions_get_todays_date_in_ddmmyyyy(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._generate_intelligent_fallback(
            {"question": "last working date"}, make_job()
        ) == today_ddmmyyyy()

    def test_achievements_and_certifications_come_from_the_resume(self, tmp_path):
        answerer = make_answerer(
            tmp_path,
            profile=make_profile(
                key_achievements=["Shipped the payments platform"],
                certifications=["Oracle Java SE"],
            ),
        )

        assert answerer._generate_intelligent_fallback(
            {"question": "key achievements"}, make_job()
        ) == "Shipped the payments platform"
        assert answerer._generate_intelligent_fallback(
            {"question": "any certification"}, make_job()
        ) == "Oracle Java SE"

    def test_defaults_used_when_resume_lacks_achievements_and_certs(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._generate_intelligent_fallback(
            {"question": "key accomplishment"}, make_job()
        ) == "Built production-grade systems and optimized application performance"
        assert answerer._generate_intelligent_fallback(
            {"question": "certified courses"}, make_job()
        ) == "Full Stack Development certification"

    def test_dob_and_marital_status_defaults(self, tmp_path):
        settings = make_settings(tmp_path, date_of_birth="", marital_status="")
        answerer = make_answerer(tmp_path, settings=settings)

        assert answerer._generate_intelligent_fallback(
            {"question": "your dob"}, make_job()
        ) == "01/01/2000"
        assert answerer._generate_intelligent_fallback(
            {"question": "marital status"}, make_job()
        ) == "Single"

    def test_dob_default_when_unset(self, tmp_path):
        settings = make_settings(tmp_path, date_of_birth="")
        answerer = make_answerer(tmp_path, settings=settings)

        assert (
            answerer._generate_intelligent_fallback({"question": "date of birth"}, make_job())
            == "01/01/2000"
        )

    def test_missing_profile_urls_fall_back_to_not_available(self, tmp_path):
        settings = make_settings(tmp_path, github_url="", linkedin_url="")
        answerer = make_answerer(tmp_path, settings=settings)

        assert answerer._generate_intelligent_fallback(
            {"question": "github handle"}, make_job()
        ) == "N/A"
        assert answerer._generate_intelligent_fallback(
            {"question": "portfolio link"}, make_job()
        ) == "N/A"
        assert answerer._generate_intelligent_fallback(
            {"question": "your website"}, make_job()
        ) == "N/A"

    def test_reason_for_change_default_when_unset(self, tmp_path):
        settings = make_settings(tmp_path, reason_for_change="")
        answerer = make_answerer(tmp_path, settings=settings)

        assert answerer._generate_intelligent_fallback(
            {"question": "reason for change"}, make_job()
        ) == "Seeking challenging role with growth opportunities"

    def test_hire_pitch_falls_back_to_generic_role(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert answerer._generate_intelligent_fallback(
            {"question": "why should we hire you"}, make_job(title="")
        ) == "1 year of hands-on experience building scalable Software Engineer solutions with modern tech stack"

    def test_empty_option_list_is_not_used_as_fallback_answer(self, tmp_path):
        answerer = make_answerer(tmp_path)

        assert (
            answerer._generate_intelligent_fallback(
                {"question": "zzzz qqqq", "type": "dropdown", "options": []}, make_job()
            )
            == "Yes"
        )

    def test_first_option_wins_for_choice_fields(self, tmp_path):
        answerer = make_answerer(tmp_path)

        answer = answerer._generate_intelligent_fallback(
            {"question": "pick one", "type": "radio", "options": [{"text": "First"}, {"text": "Second"}]},
            make_job(),
        )

        assert answer == "First"


class TestPromptFormatters:
    """Static prompt-section builders."""

    def test_education_missing(self):
        assert QuestionAnswerer._format_education([]) == "  * No formal education listed"

    def test_education_primary_keys(self):
        rendered = QuestionAnswerer._format_education(
            [{"degree": "B.Tech", "institution": "IIT Bombay", "year": "2020"}]
        )

        assert rendered == "  * B.Tech from IIT Bombay (2020)"

    def test_education_alternate_keys(self):
        rendered = QuestionAnswerer._format_education(
            [{"qualification": "MTech", "university": "BITS", "graduation_year": "2022"}]
        )

        assert rendered == "  * MTech from BITS (2022)"

    def test_education_degree_only_and_unknown_entry(self):
        assert QuestionAnswerer._format_education([{"degree": "BCA"}]) == "  * BCA"
        assert QuestionAnswerer._format_education([{}]) == "  * Unknown"
        assert QuestionAnswerer._format_education([{"institution": "MIT"}]) == "from MIT"
        assert QuestionAnswerer._format_education([{"year": "2020"}]) == "(2020)"

    def test_achievements_missing_and_truncated_to_five(self):
        assert QuestionAnswerer._format_achievements(None) == "  * No achievements listed"
        assert QuestionAnswerer._format_achievements([]) == "  * No achievements listed"

        rendered = QuestionAnswerer._format_achievements(
            ["one", "two", "three", "four", "five", "six"]
        )

        assert rendered.splitlines() == [
            "  * one",
            "  * two",
            "  * three",
            "  * four",
            "  * five",
        ]

    def test_work_experience_missing(self):
        assert QuestionAnswerer._format_work_experience([]) == "  * No work experience listed"

    def test_work_experience_primary_keys(self):
        rendered = QuestionAnswerer._format_work_experience(
            [
                {
                    "title": "Developer",
                    "company": "Acme",
                    "location": "Pune",
                    "description": "Built APIs",
                }
            ]
        )

        assert rendered == "  * Developer at Acme (Pune) : Built APIs"

    def test_work_experience_alternate_keys(self):
        rendered = QuestionAnswerer._format_work_experience(
            [{"role": "Analyst", "organization": "Globex", "summary": "Reporting"}]
        )

        assert rendered == "  * Analyst at Globex : Reporting"

    def test_work_experience_without_title_or_position_falls_back(self):
        assert QuestionAnswerer._format_work_experience([{"company": "Acme"}]) == (
            "  * Position at Acme"
        )


class TestAskAiPrompt:
    """Prompt assembly inside ``_ask_ai``."""

    @pytest.mark.asyncio
    async def test_prompt_contains_profile_job_and_questions(self, tmp_path):
        llm = make_llm("[]")
        answerer = make_answerer(
            tmp_path,
            llm=llm,
            profile=make_profile(
                education=[{"degree": "B.Tech", "institution": "IIT", "year": "2020"}],
                work_experience=[{"title": "Dev", "company": "Acme"}],
                key_achievements=["Shipped platform"],
            ),
        )

        await answerer._ask_ai([q("Favourite hobby", id="h1", type="dropdown", options=[{"text": "Chess"}])],
                              make_job(description="X" * 2500))

        kwargs = llm.generate_content.call_args.kwargs
        prompt = kwargs["prompt"]
        assert "- Full Name: Jane Developer" in prompt
        assert "- Email: jane@example.com" in prompt
        assert "- Phone: 9998887776" in prompt
        assert "- Current Title: Software Engineer" in prompt
        assert "- Preferred Locations: Bangalore, Pune (Willing to relocate: Yes)" in prompt
        assert "- Current CTC: 10 LPA" in prompt
        assert "- Expected CTC: 15 LPA (negotiable)" in prompt
        assert "- Notice Period: 30 days" in prompt
        assert "- Languages: English, Hindi" in prompt
        assert "- GitHub: https://github.com/tester" in prompt
        assert "- LinkedIn: https://linkedin.com/in/tester" in prompt
        assert "- Technical Skills: Skill0, Skill1" in prompt
        assert "Skill29, Skill30" not in prompt
        assert "  * B.Tech from IIT (2020)" in prompt
        assert "  * Dev at Acme" in prompt
        assert "  * Shipped platform" in prompt
        assert "- Title: Java Developer" in prompt
        assert "- Company: Acme Corp" in prompt
        assert '"id": "h1"' in prompt
        assert '"type": "dropdown"' in prompt
        assert "X" * 2000 in prompt
        assert "X" * 2001 not in prompt
        assert kwargs["temperature"] == 0.2
        assert kwargs["max_output_tokens"] == 2048
        assert kwargs["response_mime_type"] == "application/json"
        assert kwargs["response_schema"] == list[ScreeningAnswer]

    @pytest.mark.asyncio
    async def test_prompt_uses_not_specified_placeholders_for_blank_data(self, tmp_path):
        llm = make_llm("[]")
        answerer = make_answerer(
            tmp_path,
            llm=llm,
            settings=make_settings(
                tmp_path,
                current_ctc="",
                expected_ctc="",
                notice_period="",
                total_experience="",
                current_location="",
                preferred_locations=[],
                languages=[],
                github_url="",
                linkedin_url="",
            ),
            profile=make_profile(name="", email="", phone="", current_title="", skills=[]),
        )

        await answerer._ask_ai([q("Favourite hobby")], make_job(title="", company="", description=""))

        prompt = llm.generate_content.call_args.kwargs["prompt"]
        assert "- Full Name: Not specified" in prompt
        assert "- Email: Not specified" in prompt
        assert "- Phone: Not specified" in prompt
        assert "- Current Title: Not specified" in prompt
        assert "- Current CTC: Not specified" in prompt
        assert "- Expected CTC: Not specified (negotiable)" in prompt
        assert "- Notice Period: Not specified" in prompt
        assert "- Total Experience: 1 year (Not specified)" in prompt
        assert "- Current Location: Not specified" in prompt
        assert "- Preferred Locations: Not specified (Willing to relocate: Yes)" in prompt
        assert "- Languages: English" in prompt
        assert "- Title: Unknown" in prompt
        assert "- Company: Unknown" in prompt
        assert "- Description: Not specified" in prompt
        assert "FULL RESUME TEXT" not in prompt
        assert '"id": "q_0"' in prompt

    @pytest.mark.asyncio
    async def test_raw_resume_text_section_is_included_when_present(self, tmp_path):
        llm = make_llm("[]")
        answerer = make_answerer(
            tmp_path, llm=llm, profile=make_profile(raw_text="Dart and Flutter for 2 years.")
        )

        await answerer._ask_ai([q("Favourite hobby")], make_job())

        prompt = llm.generate_content.call_args.kwargs["prompt"]
        assert "FULL RESUME TEXT:" in prompt
        assert "Dart and Flutter for 2 years." in prompt


class TestAskAiResponseParsing:
    """JSON handling and answer matching inside ``_ask_ai``."""

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_is_accepted(self, tmp_path):
        llm = make_llm(
            '```json\n[{"question": "Favourite hobby", "answer": "Chess", "confidence": "high"}]\n```'
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai([q("Favourite hobby", index=0)], make_job())

        assert answers == [
            {
                "id": None,
                "question": "Favourite hobby",
                "answer": "Chess",
                "confidence": "high",
                "index": 0,
            }
        ]

    @pytest.mark.asyncio
    async def test_bare_fence_without_language_tag_is_accepted(self, tmp_path):
        llm = make_llm('```\n[{"question": "Favourite hobby", "answer": "Chess"}]\n```')
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai([q("Favourite hobby")], make_job())

        assert answers[0]["answer"] == "Chess"
        assert answers[0]["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_invalid_json_triggers_a_correction_prompt(self, tmp_path):
        llm = make_llm(
            "not json at all",
            '```json\n[{"question": "Favourite hobby", "answer": "Chess", "confidence": "high"}]\n```',
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai(
            [q("Favourite hobby", id="h1", type="dropdown", options=[{"text": "Chess"}])], make_job()
        )

        assert answers[0]["answer"] == "Chess"
        first_call, second_call = llm.generate_content.call_args_list
        assert first_call.kwargs["temperature"] == 0.2
        assert second_call.kwargs["temperature"] == 0.1
        assert "The previous response was not valid JSON" in second_call.kwargs["prompt"]
        assert '"id": "h1"' in second_call.kwargs["prompt"]
        assert "Return ONLY valid JSON" in second_call.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_single_object_response_is_wrapped_into_a_list(self, tmp_path):
        llm = make_llm('{"question": "Favourite hobby", "answer": "Chess", "confidence": "high"}')
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai([q("Favourite hobby")], make_job())

        assert [entry["answer"] for entry in answers] == ["Chess"]

    @pytest.mark.asyncio
    async def test_answer_is_matched_by_question_id(self, tmp_path):
        llm = make_llm(
            ai_reply({"id": "agent_q_99", "question": "Totally different wording", "answer": "Sure"}),
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai(
            [q("Why do you want to join our organization?", id="agent_q_99", index=3)], make_job()
        )

        assert answers == [
            {
                "id": "agent_q_99",
                "question": "Why do you want to join our organization?",
                "answer": "Sure",
                "confidence": "high",
                "index": 3,
            }
        ]

    @pytest.mark.asyncio
    async def test_answer_is_matched_by_normalised_question_text(self, tmp_path):
        llm = make_llm(
            ai_reply({"id": "other", "question": "Favourite hobby ?", "answer": "Chess"})
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai([q("Favourite  hobby", index=2)], make_job())

        assert answers[0]["answer"] == "Chess"
        assert answers[0]["question"] == "Favourite  hobby"
        assert answers[0]["index"] == 2

    @pytest.mark.asyncio
    async def test_unmatched_answer_falls_back_to_position(self, tmp_path):
        llm = make_llm(ai_reply({"id": "x", "question": "Something else", "answer": "Chess"}))
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai(
            [q("Favourite hobby", id="h1", index=0), q("Favourite season", id="h2", index=1)],
            make_job(),
        )

        assert answers[0] == {
            "id": "h1",
            "question": "Favourite hobby",
            "answer": "Chess",
            "confidence": "high",
            "index": 0,
        }
        assert answers[1]["answer"] == ""
        assert answers[1]["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_answer_already_matching_an_option_is_kept(self, tmp_path):
        llm = make_llm(
            ai_reply({"id": "q1", "question": "Relocate?", "answer": "No, not willing"})
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai(
            [
                q(
                    "Relocate?",
                    id="q1",
                    type="dropdown",
                    options=[{"text": "Yes, willing"}, {"text": "No, not willing"}],
                )
            ],
            make_job(),
        )

        assert answers[0]["answer"] == "No, not willing"
        assert answers[0]["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_near_miss_option_is_snapped_and_confidence_raised(self, tmp_path):
        llm = make_llm(
            ai_reply(
                {"id": "q1", "question": "Relocate?", "answer": "Yes, willing to relocate"}
            )
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai(
            [
                q(
                    "Relocate?",
                    id="q1",
                    type="dropdown",
                    options=[{"text": "Yes, I am willing to relocate"}, {"text": "No, not willing"}],
                )
            ],
            make_job(),
        )

        assert answers[0]["answer"] == "Yes, I am willing to relocate"
        assert answers[0]["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_dissimilar_option_downgrades_confidence_without_replacing(self, tmp_path):
        llm = make_llm(
            ai_reply({"id": "q1", "question": "Pick colour", "answer": "Purple", "confidence": "high"})
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai(
            [q("Pick colour", id="q1", type="dropdown", options=[{"text": "Red"}, {"text": "Green"}])],
            make_job(),
        )

        assert answers[0]["answer"] == "Purple"
        assert answers[0]["confidence"] == "low"
        assert not (tmp_path / "data" / "qa_cache.json").exists()

    @pytest.mark.asyncio
    async def test_confident_answers_are_persisted_to_the_cache_file(self, tmp_path):
        llm = make_llm(
            ai_reply({"id": "q1", "question": "Favourite hobby", "answer": "Chess", "confidence": "high"})
        )
        answerer = make_answerer(tmp_path, llm=llm)

        await answerer._ask_ai([q("Favourite hobby", id="q1")], make_job())

        assert json.loads((tmp_path / "data" / "qa_cache.json").read_text(encoding="utf-8")) == {
            "favourite hobby": "Chess"
        }

    @pytest.mark.asyncio
    async def test_low_confidence_answers_are_not_cached(self, tmp_path):
        llm = make_llm(
            ai_reply({"id": "q1", "question": "Favourite hobby", "answer": "Chess", "confidence": "low"})
        )
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai([q("Favourite hobby", id="q1")], make_job())

        assert answers[0]["confidence"] == "low"
        assert not (tmp_path / "data" / "qa_cache.json").exists()

    @pytest.mark.asyncio
    async def test_answers_are_matched_to_question_defaults_when_fields_missing(self, tmp_path):
        llm = make_llm(ai_reply([{}, "not-a-dict"]))
        answerer = make_answerer(tmp_path, llm=llm)

        answers = await answerer._ask_ai([q("Favourite hobby"), q("Favourite season")], make_job())

        assert [entry["answer"] for entry in answers] == ["", ""]
        assert [entry["confidence"] for entry in answers] == ["low", "low"]

    @pytest.mark.asyncio
    async def test_screening_answer_model_round_trips(self):
        answer = ScreeningAnswer(id="q1", question="Favourite hobby?", answer="Chess", confidence="high")

        assert answer.model_dump() == {
            "id": "q1",
            "question": "Favourite hobby?",
            "answer": "Chess",
            "confidence": "high",
        }
        assert ScreeningAnswer(question="Q", answer="A", confidence="high").id is None


class TestAskAiFailures:
    """Error branches inside ``_ask_ai``."""

    QUESTIONS = [
        q("Favourite hobby", id="h1", index=0),
        q("Favourite season", id="h2", index=1),
    ]
    EXPECTED = [
        {"id": "h1", "question": "Favourite hobby", "answer": "", "confidence": "low", "index": 0},
        {"id": "h2", "question": "Favourite season", "answer": "", "confidence": "low", "index": 1},
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failure",
        [
            LLMQuotaExceededError("daily quota", is_daily_quota=True),
            LLMQuotaExceededError("burst quota", is_daily_quota=False),
            LLMAPIError("upstream 500"),
            RuntimeError("boom"),
            "not json",
            ["still not json", "still not json either"],
        ],
        ids=["daily-quota", "rate-limit", "api-error", "unexpected", "bad-json", "bad-json-twice"],
    )
    async def test_failures_return_blank_low_confidence_entries(self, tmp_path, failure):
        replies = failure if isinstance(failure, list) else [failure]
        answerer = make_answerer(tmp_path, llm=make_llm(*replies))

        assert await answerer._ask_ai(self.QUESTIONS, make_job()) == self.EXPECTED

    @pytest.mark.asyncio
    async def test_quota_and_api_errors_are_logged(self, tmp_path, caplog):
        answerer = make_answerer(
            tmp_path, llm=make_llm(LLMQuotaExceededError("daily", is_daily_quota=True))
        )

        with caplog.at_level("ERROR", logger="src.naukri_agent.ai.question_answerer"):
            await answerer._ask_ai(self.QUESTIONS, make_job())

        assert "Gemini daily quota exhausted" in caplog.text
        assert "daily" in caplog.text

    @pytest.mark.asyncio
    async def test_rate_limit_and_unexpected_failures_are_logged(self, tmp_path, caplog):
        answerer = make_answerer(
            tmp_path, llm=make_llm(LLMQuotaExceededError("burst", is_daily_quota=False))
        )
        with caplog.at_level("ERROR", logger="src.naukri_agent.ai.question_answerer"):
            await answerer._ask_ai(self.QUESTIONS, make_job())
        assert "Gemini rate limit hit" in caplog.text

        answerer = make_answerer(tmp_path, llm=make_llm(RuntimeError("kaboom")))
        with caplog.at_level("ERROR", logger="src.naukri_agent.ai.question_answerer"):
            await answerer._ask_ai(self.QUESTIONS, make_job())
        assert "AI question answering failed: kaboom" in caplog.text

    @pytest.mark.asyncio
    async def test_api_error_message_is_logged_verbatim(self, tmp_path, caplog):
        answerer = make_answerer(tmp_path, llm=make_llm(LLMAPIError("gemini 503 unavailable")))

        with caplog.at_level("ERROR", logger="src.naukri_agent.ai.question_answerer"):
            await answerer._ask_ai(self.QUESTIONS, make_job())

        assert "gemini 503 unavailable" in caplog.text

    @pytest.mark.asyncio
    async def test_failure_after_retry_still_returns_blank_entries(self, tmp_path, caplog):
        answerer = make_answerer(tmp_path, llm=make_llm("{oops", "]]] not json"))
        llm_holder = answerer._llm

        with caplog.at_level("WARNING", logger="src.naukri_agent.ai.question_answerer"):
            answers = await answerer._ask_ai(self.QUESTIONS, make_job())

        assert answers == self.EXPECTED
        assert "JSON parse failed, retrying with correction prompt" in caplog.text
        assert llm_holder.generate_content.call_count == 2


