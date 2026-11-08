"""Best-effort screening answers keep every field populated."""

from libs.common.screening_fallback import numeric_answer, positive_answer
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


def test_ctc_text_fields_become_plain_inr_numbers(tmp_path):
    profile = {"current_ctc": "4.4 lpa", "expected_ctc": "6 lpa"}
    current = {"question": "Please enter your current ctc in INR", "field_type": "text"}
    expected = {"question": "Please enter your expected ctc in INR", "field_type": "text"}
    assert answer(tmp_path, current, profile) == "440000"
    assert answer(tmp_path, expected, profile) == "600000"


def test_notice_field_without_the_word_day_stays_numeric(tmp_path):
    question = {"question": "Notice period", "field_type": "text"}
    assert answer(tmp_path, question, {"notice_period": "2 weeks"}) == "14"


def test_location_text_fields_use_the_saved_city(tmp_path):
    question = {"question": "Location (city)*", "field_type": "text"}
    assert answer(tmp_path, question, {"current_city": "Pune"}) == "Pune"


def test_experience_questions_mentioning_github_actions_stay_numeric(tmp_path):
    question = {
        "question": "How many years of work experience do you have in DevOps "
        "(AWS, Jenkins, GitHub Actions)?",
        "field_type": "text",
    }
    assert answer(tmp_path, question, {"total_experience": "1 year"}) == "1"


def test_a_bare_github_question_still_returns_the_profile_link(tmp_path):
    question = {"question": "GitHub", "field_type": "text"}
    assert answer(tmp_path, question) == "https://github.com/candidate"


def test_numeric_retry_answer_is_never_prose(tmp_path):
    settings = Settings(project_root=tmp_path, profile={})
    question = {
        "question": "Have you worked on AEM architecture and implementation?",
        "field_type": "text",
    }
    value = numeric_answer(question, settings, candidate())
    assert value.isdigit()
    assert int(value) >= 1


def test_monthly_expected_rate_uses_the_annual_expected_ctc(tmp_path):
    profile = {"expected_ctc": "6 lpa"}
    question = {
        "question": "Monthly expected rate in INR (As per Gov. 10% TDS would be deducted):",
        "field_type": "text",
    }
    assert answer(tmp_path, question, profile) == "50000"


def test_numeric_retry_uses_the_expected_ctc_for_a_monthly_rate(tmp_path):
    settings = Settings(project_root=tmp_path, profile={"expected_ctc": "6 lpa"})
    question = {
        "question": "Monthly expected rate in INR (As per Gov. 10% TDS would be deducted):",
        "field_type": "text",
    }
    assert numeric_answer(question, settings, candidate()) == "50000"
