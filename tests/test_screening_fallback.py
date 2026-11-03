"""Best-effort screening answers keep every field populated."""

from libs.common.screening_fallback import positive_answer
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile


def candidate():
    return ResumeProfile(
        name="Candidate",
        current_title="Software Engineer",
        total_experience_years=1,
        skills=["Java", "Spring Boot", "SQL"],
        raw_text="Pune | linkedin.com/in/candidate | github.com/candidate",
    )


def job():
    return Job(
        "123456789012",
        "Java Developer",
        "Example employer",
        "https://example.invalid/job",
        skills="Java, Spring Boot, SQL",
        id=1,
    )


def answer(tmp_path, question, profile=None):
    settings = Settings(project_root=tmp_path, profile=profile or {})
    return positive_answer(question, settings, candidate(), job())


def test_plain_yes_no_questions_are_answered_yes(tmp_path):
    assert (
        answer(tmp_path, {"question": "Are you willing to relocate?", "options": ["Yes", "No"]})
        == "Yes"
    )


def test_sponsorship_questions_are_answered_no(tmp_path):
    question = {
        "question": "Will you now or in the future require visa sponsorship?",
        "options": ["Yes", "No"],
    }
    assert answer(tmp_path, question) == "No"


def test_a_lone_consent_checkbox_is_checked(tmp_path):
    question = {
        "question": "You declare that you have read and agree to the privacy notice.*",
        "field_type": "checkbox",
        "options": ["You declare that you have read and agree to the privacy notice."],
    }
    assert answer(tmp_path, question) == "Yes"


def test_demographic_questions_prefer_the_decline_option(tmp_path):
    question = {
        "question": "Do you have a disability?",
        "field_type": "dropdown",
        "options": ["Yes", "No", "I don't wish to answer"],
    }
    assert answer(tmp_path, question) == "I don't wish to answer"


def test_location_choices_use_a_configured_preference(tmp_path):
    question = {
        "question": "Select Your Preferred Work Location*",
        "field_type": "radio",
        "options": ["Noida, Uttar Pradesh, India", "Mumbai, Maharashtra, India"],
    }
    assert answer(tmp_path, question, {"preferred_locations": ["Pune", "Mumbai"]}) == (
        "Mumbai, Maharashtra, India"
    )


def test_experience_scale_uses_the_stated_total(tmp_path):
    question = {
        "question": "How many years of professional experience do you have?",
        "field_type": "dropdown",
        "options": ["0 years", "1 year", "2 years", "3 years"],
    }
    assert answer(tmp_path, question, {"total_experience": "1 year"}) == "1 year"


def test_notice_period_days_use_the_saved_notice(tmp_path):
    question = {"question": "Please enter your notice period in days", "field_type": "text"}
    assert answer(tmp_path, question, {"notice_period": "30 days"}) == "30"
    assert answer(tmp_path, question, {"notice_period": "Immediate"}) == "0"


def test_narrative_questions_get_a_grounded_draft(tmp_path):
    question = {"question": "Why do you want to join our company?", "field_type": "text"}
    assert len(answer(tmp_path, question)) > 30


def test_profile_links_come_from_the_resume_text(tmp_path):
    question = {"question": "Please enter your LinkedIn profile URL", "field_type": "text"}
    assert answer(tmp_path, question) == "https://linkedin.com/in/candidate"
