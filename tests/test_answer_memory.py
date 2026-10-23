import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from libs.common.screening_memory import filled_answer, local_answer, profile_context
from libs.common.screening_review import ScreeningReviewStore
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile


def job(identifier="123456789012"):
    return Job(identifier, "Java Developer", "Example", "https://example.test/job", id=1)


def test_profile_answers_persist_and_refresh_instead_of_resurrecting_old_salary(tmp_path):
    settings = Settings(project_root=tmp_path, profile={"expected_ctc": "8 LPA"})
    candidate = ResumeProfile()
    question = {"question": "Expected CTC in LPA", "type": "number"}
    assert local_answer(question, settings, candidate, job())[0] == "8"
    store = ScreeningReviewStore(tmp_path)
    assert store.memory()["items"][0]["source"] == "profile"
    assert not store.pending()
    assert local_answer(question, settings, candidate, job())[0] == "8"
    assert store.memory()["items"][0]["use_count"] == 1
    old_context = profile_context(settings, candidate)
    settings.profile.expected_ctc = "9 LPA"
    assert not store.answer_for(question, job(), profile_context(settings, candidate))
    assert local_answer(question, settings, candidate, job())[0] == "9"
    assert store.memory()["items"][0]["answer"] == "9"
    assert not store.answer_for(question, job(), old_context)


def test_ai_suggestions_need_confirmation_and_corrections_survive_restart(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    question = {"question": "Are you willing to travel?", "options": ["Yes", "No"]}
    identifier = store.observe(question, "Yes", job(), "ai_suggestion", "same-profile")
    assert not store.answer_for(question, job(), "same-profile")
    store.save_answers({identifier: "No"})
    restarted = ScreeningReviewStore(tmp_path)
    assert restarted.answer_for(question, job(), "changed-profile") == "No"
    assert restarted.memory()["items"][0]["source"] == "confirmed"
    restarted.save_answers({identifier: "Yes"})
    assert ScreeningReviewStore(tmp_path).answer_for(question, job()) == "Yes"


def test_latest_correction_never_falls_back_to_an_older_incompatible_variant(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    numeric = {"question": "Custom experience in years", "type": "number"}
    choice = {
        "question": numeric["question"],
        "type": "dropdown",
        "options": ["0-2 years", "3-5 years"],
    }
    old = store.remember(numeric, job())
    store.save_answers({old: "1"})
    new = store.remember(choice, job())
    store.save_answers({new: "3-5 years"})
    assert not store.answer_for(numeric, job())
    assert store.answer_for(choice, job()) == "3-5 years"
    store.forget(new)
    assert store.memory()["total"] == 0
    assert not store.answer_for(numeric, job())


def test_memory_preserves_language_units_job_and_tenant_boundaries(tmp_path):
    store = ScreeningReviewStore(tmp_path / "one")
    q = {"question": "C++ experience in years", "type": "number"}
    identifier = store.remember(q, job())
    store.save_answers({identifier: "1"})
    assert not store.answer_for({**q, "question": "C# experience in years"}, job())
    assert not store.answer_for({**q, "question": "C++ experience in months"}, job())
    motivation = {"question": "Why should we hire you?"}
    identifier = store.remember(motivation, job())
    store.save_answers({identifier: "My Java skills match this published role."})
    assert not store.answer_for(motivation, job("999999999999"))
    linkedin = SimpleNamespace(linkedin_job_id="123456789012", id=1)
    assert not store.answer_for(motivation, linkedin)
    other = ScreeningReviewStore(tmp_path / "two")
    with pytest.raises(ValueError):
        other.forget(identifier)
    assert store.answer_for(motivation, job())


@pytest.mark.parametrize("platform", ["naukri", "linkedin"])
@pytest.mark.parametrize("gemini", [False, True])
async def test_both_platforms_reuse_one_confirmation_in_all_ai_modes(tmp_path, platform, gemini):
    question = {
        "question": "Are you willing to travel?",
        "type": "text",
        "field_type": "text",
        "options": ["Yes", "No"],
    }
    store = ScreeningReviewStore(tmp_path)
    identifier = store.remember(question, job())
    store.save_answers({identifier: "No"})
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("Known memory must not call Gemini")
    if platform == "naukri":
        from src.naukri_agent.ai.question_answerer import QuestionAnswerer

        settings = Settings(project_root=tmp_path, ai={"use_gemini": gemini})
        answerer = QuestionAnswerer(provider, settings, ResumeProfile())
    else:
        from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
        from src.linked_agent.config.settings import Settings as LinkedInSettings

        settings = LinkedInSettings(project_root=tmp_path, ai={"use_gemini": gemini})
        answerer = LinkedInQuestionAnswerer(provider, settings, ResumeProfile())
    assert (await answerer.answer_questions([question], job()))[0]["answer"] == "No"
    assert ScreeningReviewStore(tmp_path).memory()["items"][0]["use_count"] == 1
    provider.generate_content.assert_not_called()


def test_existing_answer_database_migrates_without_losing_confirmations(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    with sqlite3.connect(store.path) as db:
        db.execute(
            "CREATE TABLE questions(id TEXT PRIMARY KEY,question_key TEXT,question TEXT,field_type TEXT,options TEXT,answer TEXT,updated_at TEXT)"
        )
        db.execute(
            "INSERT INTO questions VALUES('legacy','custom fact','Custom fact','text','[]','Saved fact','2026-01-01')"
        )
    assert store.answer_for({"question": "Custom fact"}, job()) == "Saved fact"
    assert store.memory()["items"][0]["use_count"] == 1


def test_employer_memory_records_accepted_values_not_uncommitted_suggestions():
    dropdown = {"type": "dropdown", "value": "n", "options": [{"text": "No", "value": "n"}]}
    assert filled_answer(dropdown, "No") == "No"
    assert not filled_answer(dropdown, "Yes")
    assert filled_answer({"type": "checkbox", "value": ""}, "No") == "No"
    assert not filled_answer({"type": "checkbox", "value": ""}, "Yes")
    assert (
        filled_answer({"type": "skill_tags", "value": "Java, SQL"}, "Java, SQL, Unknown")
        == "Java, SQL"
    )
    assert not filled_answer({"type": "text", "value": "Rejected"}, "Saved answer")
