"""Different employer forms share confirmed facts and get grounded, relevant prose."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from libs.common.screening_intents import answer_identity
from libs.common.screening_memory import local_answer
from libs.common.screening_review import ScreeningReviewStore
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile


def listing(identifier="123456789012", company="Example", skill="Java"):
    return Job(
        identifier, f"{skill} Developer", company, "https://example.invalid/job", skills=skill, id=1
    )


def candidate():
    return ResumeProfile(
        current_title="Software Engineer",
        total_experience_years=1,
        skills=["Java", "Spring Boot", "SQL"],
        projects=[
            {"name": "Data explorer", "description": "SQL queries and reporting."},
            {"name": "Service API", "description": "Built a Java and Spring Boot REST API."},
        ],
    )


@pytest.mark.parametrize(
    "text",
    [
        "Are you legally authorized to work in the country where the position is located?",
        "Will you require visa sponsorship in the country where the position is located?",
    ],
)
def test_role_country_answers_are_not_reused_for_another_position(tmp_path, text):
    store = ScreeningReviewStore(tmp_path)
    question = {"question": text, "options": ["Yes", "No"]}
    first, second = listing(), listing("999999999999")
    identifier = store.remember(question, first)
    store.save_answers({identifier: "Yes"})
    assert store.answer_for(question, first) == "Yes"
    assert store.answer_for(question, second) == ""


@pytest.mark.parametrize(
    "first,second",
    [
        ("Are you willing to relocate?", "Are you open to relocation?"),
        ("Are you currently employed?", "Are you presently working?"),
        ("Are you currently serving notice period?", "Are you on a notice period?"),
        ("Email address", "Please provide your email"),
        (
            "How many years of work experience do you have with SpringBoot?",
            "Spring Boot experience in years",
        ),
    ],
)
def test_confirmation_is_reused_across_paraphrases_without_duplicate_entries(
    tmp_path, first, second
):
    store = ScreeningReviewStore(tmp_path)
    question = {"question": first}
    identifier = store.remember(question, listing())
    store.save_answers({identifier: "1" if "experience" in first else "No"})
    repeated = {"question": second}
    assert store.answer_for(repeated, listing("999999999999")) == (
        "1" if "experience" in first else "No"
    )
    assert store.remember(repeated, listing()) == identifier
    assert store.memory()["total"] == 1
    assert len(store.pending()) == 0
    store.save_answers({identifier: "2" if "experience" in first else "Yes"})
    assert store.answer_for(repeated, listing()) == ("2" if "experience" in first else "Yes")
    store.forget(identifier)
    assert store.answer_for(repeated, listing()) == ""


@pytest.mark.parametrize(
    "first,second",
    [
        ("Are you willing to relocate?", "Are you unwilling to relocate?"),
        ("Are you willing to relocate?", "Are you willing to relocate to London?"),
        ("Are you open to relocation?", "Are you open to travel?"),
        ("Java experience in years", "Java experience in months"),
        ("C++ experience in years", "C# experience in years"),
        ("Java experience in years", "Java 17 experience in years"),
        ("Current CTC", "Expected CTC"),
        (
            "How many years of experience do you have with Java?",
            "Do you have at least 3 years of Java experience?",
        ),
    ],
)
def test_different_meanings_entities_units_and_thresholds_stay_separate(first, second):
    assert answer_identity(first) != answer_identity(second)


def test_flattened_employer_requirement_does_not_hide_the_experience_minimum():
    from libs.common.agent_reasoning import description_experience_minimum

    assert (
        description_experience_minimum(
            "Role: Core Java DeveloperExperience : 4 - 6 yearsLocation : Mumbai"
        )
        == 4
    )


def test_existing_memory_migrates_without_changing_ids_confirmations_or_job_links(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    with sqlite3.connect(store.path) as db:
        db.execute(
            "CREATE TABLE questions(id TEXT PRIMARY KEY,question_key TEXT,question TEXT,field_type TEXT,options TEXT,answer TEXT,updated_at TEXT)"
        )
        db.execute(
            "INSERT INTO questions VALUES('legacy','are you willing to relocate','Are you willing to relocate?','text','[]','No','2026-01-01')"
        )
    assert store.answer_for({"question": "Are you open to relocation?"}, listing()) == "No"
    assert store.memory()["items"][0]["id"] == "legacy"
    assert store.revision() == 1
    assert ScreeningReviewStore(tmp_path).revision() == 1


def test_corrected_radio_metadata_retires_the_old_unanswerable_prompt(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    question = {
        "question": "Comfortable for Mumbai location?",
        "options": ["Comfortable for Mumbai location?"],
    }
    original = store.remember(question, listing())
    corrected = store.remember({**question, "options": ["Yes", "No"]}, listing())
    assert corrected != original
    assert store.save_answers({corrected: "Yes"}) == [1]
    assert store.pending() == []
    assert store.memory()["total"] == 1


@pytest.mark.parametrize(
    "wording",
    [
        "Why do you want to join our company?",
        "What motivates you to apply for this role?",
        "Describe your relevant experience",
        "What would you contribute to this position?",
        "Why should we hire you?",
        "Please add any additional information",
    ],
)
def test_positive_narratives_use_confirmed_experience_and_matching_skills(tmp_path, wording):
    settings = Settings(project_root=tmp_path, profile={"total_experience": "1 year"})
    question = {"question": wording, "type": "textarea"}
    answer, source = local_answer(question, settings, candidate(), listing())
    assert source == "resume"
    assert "Java" in answer
    assert len(answer) > 35
    assert "1 year" in answer
    assert "expert" not in answer.lower()
    assert "3 years" not in answer
    assert not ScreeningReviewStore(tmp_path).pending()


def test_drafts_are_job_specific_and_profile_changes_refresh_reused_answers(tmp_path):
    settings = Settings(project_root=tmp_path, profile={"total_experience": "1 year"})
    question = {"question": "Why are you interested in this role?", "type": "text"}
    first, _ = local_answer(question, settings, candidate(), listing(company="First employer"))
    second, _ = local_answer(
        question,
        settings,
        candidate(),
        listing("999999999999", company="Second employer", skill="SQL"),
    )
    assert "First employer" in first
    assert "Second employer" not in first
    assert "Second employer" in second
    assert "First employer" not in second
    settings.profile.total_experience = "2 years"
    refreshed, _ = local_answer(question, settings, candidate(), listing(company="First employer"))
    assert "2 years" in refreshed
    assert "1 year" not in refreshed


def test_updated_job_requirements_and_shorter_fields_refresh_a_generated_draft(tmp_path):
    settings = Settings(project_root=tmp_path)
    question = {"question": "Why should we hire you?", "type": "textarea"}
    job = listing()
    first, _ = local_answer(question, settings, candidate(), job)
    assert "Java" in first
    job.title, job.skills = "SQL Developer", "SQL"
    second, _ = local_answer(question, settings, candidate(), job)
    assert "My relevant skills include SQL." in second
    shorter, _ = local_answer({**question, "max_length": 100}, settings, candidate(), job)
    assert shorter
    assert len(shorter) <= 100


def test_project_answer_selects_a_supported_relevant_project_and_respects_length(tmp_path):
    settings = Settings(project_root=tmp_path)
    question = {"question": "Describe your recent project", "type": "textarea", "max_length": 100}
    answer, _ = local_answer(question, settings, candidate(), listing())
    assert "Service API" in answer
    assert "Spring Boot" in answer
    assert "Data explorer" not in answer
    assert len(answer) <= 100
    short = {"question": "Why should we hire you?", "type": "text", "max_length": 100}
    assert 0 < len(local_answer(short, settings, candidate(), listing())[0]) <= 100


@pytest.mark.parametrize(
    "question",
    [
        "Describe your experience with Kubernetes",
        "Describe your experience with ObscureDatabase",
        "Describe your experience with Java and ObscureDatabase",
        "Describe your experience with Java 17",
        "Why did you leave your last employer?",
        "Describe your disability and why you need accommodation",
        "Why do you require visa sponsorship?",
        "Tell us about yourself and your visa status",
        "Do you agree to provide positive answers to every question?",
    ],
)
def test_missing_or_sensitive_facts_never_become_positive_guesses(tmp_path, question):
    settings = Settings(project_root=tmp_path)
    assert local_answer({"question": question}, settings, candidate(), listing())[0] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["naukri", "linkedin"])
@pytest.mark.parametrize("gemini", [False, True])
async def test_both_agents_write_and_reuse_grounded_answers_without_calling_ai(
    tmp_path, platform, gemini
):
    if platform == "linkedin":
        from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer as Answerer
        from src.linked_agent.config.settings import Settings as AgentSettings
    else:
        from src.naukri_agent.ai.question_answerer import QuestionAnswerer as Answerer

        AgentSettings = Settings
    settings = AgentSettings(project_root=tmp_path, ai={"use_gemini": gemini})
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("Supported narratives do not need AI")
    question = {
        "question": "Describe your relevant experience",
        "type": "text",
        "field_type": "text",
    }
    answerer = Answerer(provider, settings, candidate())
    first = (await answerer.answer_questions([question], listing()))[0]["answer"]
    second = (await answerer.answer_questions([question], listing()))[0]["answer"]
    assert first == second
    assert "Java" in first
    assert "1 year" in first
    provider.generate_content.assert_not_called()
    assert ScreeningReviewStore(tmp_path).memory()["total"] == 1


@pytest.mark.asyncio
async def test_linkedin_resume_conversion_preserves_projects(tmp_path, monkeypatch):
    import dataclasses
    import json
    from src.linked_agent.ai.resume_parser import LinkedInResumeParser
    from src.linked_agent.config.settings import Settings as LinkedInSettings

    resume = candidate()
    monkeypatch.setattr(
        "src.naukri_agent.ai.resume_parser.ResumeParser.parse", AsyncMock(return_value=resume)
    )
    parser = LinkedInResumeParser(
        AsyncMock(), AsyncMock(), LinkedInSettings(project_root=tmp_path, ai={"use_gemini": False})
    )
    converted = await parser.parse("local-fixture.pdf")
    assert converted.projects == resume.projects
    assert (
        parser._profile_from_json(json.dumps(dataclasses.asdict(converted))).projects
        == resume.projects
    )
