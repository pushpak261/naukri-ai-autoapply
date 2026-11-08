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
        education=[
            {"degree": "B.E., Mechanical Engineering", "institution": "Example", "year": "2023"},
            {"degree": "PG-DAC", "institution": "CDAC", "year": "2024"},
        ],
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


def test_skill_ratings_are_not_mistaken_for_pay(tmp_path):
    question = {"question": "Rate your Java skills from 1 to 10", "field_type": "text"}
    value = answer(tmp_path, question, {"expected_ctc": "6 lpa"})
    assert value
    assert value != "50000"


def test_full_name_and_highest_degree_come_from_the_resume(tmp_path):
    name = {"question": "Please enter your full name.", "field_type": "text"}
    degree = {"question": "Please specify your highest completed degree", "field_type": "text"}
    assert answer(tmp_path, name) == "Candidate"
    assert answer(tmp_path, degree) == "PG-DAC"


def test_where_are_you_based_returns_the_saved_city(tmp_path):
    question = {"question": "Where are you currently based?", "field_type": "text"}
    assert answer(tmp_path, question, {"current_city": "Pune"}) == "Pune"


def test_last_working_day_uses_the_saved_date_or_immediate(tmp_path):
    question = {
        "question": "If you are serving notice, what will be your last working day?",
        "field_type": "text",
    }
    assert answer(tmp_path, question) == "Immediate"
    assert answer(tmp_path, question, {"last_working_date": "2026-11-30"}) == "2026-11-30"


def test_last_working_day_is_not_overwritten_with_a_numeric_zero(tmp_path):
    from libs.common.screening_fallback import needs_numeric, numeric_answer
    from src.linked_agent.config.settings import Settings

    question = {
        "question": "If you are serving notice, what will be your last working day?",
        "field_type": "text",
    }
    settings = Settings(project_root=tmp_path, profile={"notice_period": "Immediate"})
    assert needs_numeric(question) is False
    assert numeric_answer(question, settings) == ""
    # A plain notice-period question still needs a number.
    assert needs_numeric({"question": "What will be your notice period?", "field_type": "text"})
    assert numeric_answer(
        {"question": "What will be your notice period?", "field_type": "text"}, settings
    ) == "0"


def test_start_date_questions_answer_immediate(tmp_path):
    for prompt in (
        "When can you start?",
        "What is your availability to start?",
        "What is your earliest start date?",
        "What is your date of joining?",
    ):
        question = {"question": prompt, "field_type": "text"}
        assert answer(tmp_path, question) == "Immediate", prompt
    question = {"question": "When can you start?", "field_type": "text"}
    assert answer(tmp_path, question, {"last_working_date": "2026-11-30"}) == "2026-11-30"


def test_rating_questions_get_a_high_number(tmp_path):
    ten = {
        "question": "How would you rate your communication and interpersonal skills "
        "on a scale of 1-10?",
        "field_type": "text",
    }
    five = {"question": "Rate your Java skills from 1 to 5", "field_type": "text"}
    assert answer(tmp_path, ten) == "10"
    assert answer(tmp_path, five) == "5"


def test_team_size_questions_get_a_positive_number(tmp_path):
    question = {
        "question": "Have you managed teams before? If yes, with how many people?",
        "field_type": "text",
    }
    assert answer(tmp_path, question) == "2"


def test_technology_list_questions_return_skills_not_prose(tmp_path):
    question = {
        "question": "Please list the primary technologies you have hands-on experience with.",
        "field_type": "text",
    }
    value = answer(tmp_path, question)
    assert "Java" in value and "Spring Boot" in value
    assert not value.lower().startswith("software engineer with")


def test_month_questions_use_total_months_of_experience(tmp_path):
    question = {"question": "How many months of experience do you have with Java?", "field_type": "text"}
    assert answer(tmp_path, question, {"total_experience": "2 years"}) == "24"


def test_reason_for_seeking_gets_a_motivation_draft(tmp_path):
    question = {"question": "What is your primary reason for seeking a new job?", "field_type": "text"}
    value = answer(tmp_path, question)
    assert len(value) > 30
    assert "interested" in value.lower()


def test_ctc_in_lpa_keeps_the_lpa_unit(tmp_path):
    question = {"question": "What is your expected CTC in LPA?", "field_type": "text"}
    assert answer(tmp_path, question, {"expected_ctc": "6 lpa"}) == "6"


def test_needs_numeric_separates_numbers_from_prose():
    from libs.common.screening_fallback import needs_numeric

    assert needs_numeric(
        {"question": "How many years of experience do you have?", "field_type": "text"}
    )
    assert needs_numeric(
        {
            "question": "How would you rate your communication skills on a scale of 1-10?",
            "field_type": "text",
        }
    )
    assert not needs_numeric(
        {"question": "Where are you currently based?", "field_type": "text"}
    )
