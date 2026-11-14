"""Best-effort screening answers keep every field populated."""

from dataclasses import replace

from libs.common.screening_fallback import needs_numeric, numeric_answer, positive_answer
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


def test_privacy_notice_declaration_is_consent_not_a_notice_period(tmp_path):
    question = {
        "question": (
            "You declare that you have read and understand the job applications "
            "privacy notice of METRO/MAKRO.*"
        ),
        "field_type": "text",
    }
    assert answer(tmp_path, question) == "Yes"
    assert not needs_numeric(question)


def test_prompt_echoed_as_the_only_option_is_not_an_answer(tmp_path):
    question = {
        "question": "Select Your Preferred Work Location*",
        "field_type": "text",
        "options": ["Select Your Preferred Work Location"],
    }
    assert answer(tmp_path, question, {"current_city": "Pune"}) == "Pune"


def test_privacy_consent_options_choose_the_accepting_label(tmp_path):
    question = {
        "question": "You declare that you have read and agree to the privacy notice.*",
        "field_type": "radio",
        "options": ["I do not consent", "I consent"],
    }
    assert answer(tmp_path, question) == "I consent"


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


def test_rating_dropdowns_pick_the_top_of_the_scale(tmp_path):
    numeric = {
        "question": "How would you rate your communication skills on a scale of 1-10?",
        "field_type": "dropdown",
        "options": [str(value) for value in range(1, 11)],
    }
    labelled = {
        "question": "Rate your Java skills from 1 to 5",
        "field_type": "radio",
        "options": ["1 - Poor", "3 - Average", "5 - Excellent"],
    }
    words = {
        "question": "How would you rate your communication skills?",
        "field_type": "dropdown",
        "options": ["Poor", "Average", "Excellent"],
    }
    assert answer(tmp_path, numeric) == "10"
    assert answer(tmp_path, labelled) == "5 - Excellent"
    assert answer(tmp_path, words) == "Excellent"


def test_team_size_dropdowns_pick_a_positive_range(tmp_path):
    question = {
        "question": "Have you managed teams before? If yes, with how many people?",
        "field_type": "dropdown",
        "options": ["0", "1-2", "3-5"],
    }
    assert answer(tmp_path, question) == "1-2"


def test_expected_ctc_dropdowns_pick_the_range_containing_the_fact(tmp_path):
    question = {
        "question": "What is your expected CTC?",
        "field_type": "dropdown",
        "options": ["0-5 LPA", "5-10 LPA", "10-15 LPA"],
    }
    profile = {"current_ctc": "4.4 lpa", "expected_ctc": "6 lpa"}
    assert answer(tmp_path, question, profile) == "5-10 LPA"
    current = {
        "question": "What is your current annual compensation?",
        "field_type": "dropdown",
        "options": ["0-5 LPA", "5-10 LPA", "10-15 LPA"],
    }
    assert answer(tmp_path, current, profile) == "0-5 LPA"
    monthly = {
        "question": "What is your expected monthly salary?",
        "field_type": "dropdown",
        "options": ["30,000 - 40,000 per month", "50,000 - 60,000 per month"],
    }
    assert answer(tmp_path, monthly, profile) == "50,000 - 60,000 per month"


def test_immediate_notice_picks_the_lowest_available_range(tmp_path):
    question = {
        "question": "What is your notice period?",
        "field_type": "dropdown",
        "options": ["16-30 days", "31-60 days"],
    }
    assert answer(tmp_path, question, {"notice_period": "Immediate"}) == "16-30 days"


def test_immediate_notice_prefers_the_immediate_option_over_a_numeric_range(tmp_path):
    joiner = {
        "question": "What will be your notice period?*",
        "field_type": "dropdown",
        "options": ["Serving Notice Period", "Immediate Joiner", "30 Days", "45 Days"],
    }
    available = {
        "question": "What's your current notice period?",
        "field_type": "dropdown",
        "options": ["Available Immediately", "7 days", "15 days"],
    }
    profile = {"notice_period": "Immediate"}
    assert answer(tmp_path, joiner, profile) == "Immediate Joiner"
    assert answer(tmp_path, available, profile) == "Available Immediately"


def test_serving_notice_dropdown_follows_the_saved_notice_period(tmp_path):
    question = {
        "question": "Are you currently serving your notice?*",
        "field_type": "dropdown",
        "options": ["Yes", "No"],
    }
    assert answer(tmp_path, question, {"notice_period": "Immediate"}) == "No"
    assert answer(tmp_path, question, {"notice_period": "30 days"}) == "Yes"
    assert answer(tmp_path, question, {"serving_notice": True}) == "Yes"
    assert answer(tmp_path, question, {"serving_notice": False}) == "No"
    checkbox = {**question, "field_type": "checkbox"}
    assert answer(tmp_path, checkbox, {"notice_period": "Immediate"}) == "No"


def test_serving_notice_text_question_answers_yes_or_no_not_a_duration(tmp_path):
    question = {"question": "Are you currently serving your notice?", "field_type": "text"}
    assert answer(tmp_path, question, {"notice_period": "Immediate"}) == "No"
    assert answer(tmp_path, question, {"notice_period": "2 months"}) == "Yes"


def test_serving_notice_yes_no_options_are_never_rewritten_as_a_number(tmp_path):
    question = {
        "question": "Serving Notice Period?*",
        "field_type": "text",
        "options": ["Yes", "No"],
    }
    settings = Settings(project_root=tmp_path, profile={"notice_period": "30 days"})
    assert answer(tmp_path, question, {"notice_period": "30 days"}) == "Yes"
    assert not needs_numeric(question)
    assert numeric_answer(question, settings, candidate()) == ""


def test_offer_in_hand_is_not_claimed_by_default(tmp_path):
    choice = {
        "question": "Do You Have Any Offer in Hand?*",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    text = {"question": "Do You Have Any Offer in Hand?*", "field_type": "text"}
    assert answer(tmp_path, choice) == "No"
    assert answer(tmp_path, text) == "No"
    assert answer(tmp_path, {**choice, "field_type": "checkbox"}) == "No"


def test_specific_skill_experience_is_zero_when_the_resume_lacks_it(tmp_path):
    unsupported = {
        "question": "How many years of hands-on AEM development experience do you have?",
        "field_type": "text",
    }
    supported = {
        "question": "How many years of experience do you have with Java?",
        "field_type": "text",
    }
    generic = {
        "question": "How many years of professional experience do you have?",
        "field_type": "text",
    }
    assert answer(tmp_path, unsupported) == "0"
    assert answer(tmp_path, supported) == "1"
    assert answer(tmp_path, generic) == "1"


def test_multi_select_skill_checkboxes_pick_supported_options(tmp_path):
    question = {
        "question": "Which of the following technologies do you have experience with?",
        "field_type": "checkbox",
        "options": ["Java", "Spring Boot", "Salesforce", "SQL"],
    }
    assert answer(tmp_path, question) == "Java\nSpring Boot\nSQL"


def test_multi_select_location_checkboxes_pick_preferred_cities(tmp_path):
    question = {
        "question": "Which locations are you willing to work in?",
        "field_type": "checkbox",
        "options": ["Pune", "Mumbai", "Delhi"],
    }
    profile = {"preferred_locations": ["Pune", "Mumbai"]}
    assert answer(tmp_path, question, profile) == "Pune\nMumbai"


def test_availability_to_join_answers_immediate_not_zero(tmp_path):
    question = {"question": "Available time to join/Notice Period?", "field_type": "text"}
    assert answer(tmp_path, question, {"notice_period": "Immediate"}) == "Immediate"
    assert numeric_answer(question, Settings(project_root=tmp_path, profile={})) == ""


def test_years_of_experience_managing_people_is_not_team_size(tmp_path):
    question = {
        "question": "How many years of experience do you have managing people?",
        "field_type": "text",
    }
    assert answer(tmp_path, question, {"total_experience": "5 years"}) == "5"


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


def test_additional_experience_is_zero(tmp_path):
    months = {
        "question": "Please select your total additional months of experience",
        "field_type": "dropdown",
        "options": ["0 months", "1-6 months", "7-12 months", "12+ months"],
    }
    years = {
        "question": "Please select your total additional years of experience",
        "field_type": "dropdown",
        "options": ["0 years", "1 year", "2 years"],
    }
    text = {
        "question": "Please enter your total additional months of experience",
        "field_type": "text",
    }
    assert answer(tmp_path, months) == "0 months"
    assert answer(tmp_path, years) == "0 years"
    assert answer(tmp_path, text, {"total_experience": "2 years"}) == "0"
    settings = Settings(project_root=tmp_path, profile={"total_experience": "2 years"})
    assert numeric_answer(text, settings, candidate()) == "0"


def test_experience_ranges_cover_the_saved_total(tmp_path):
    question = {
        "question": "Please select your total years of professional experience",
        "field_type": "dropdown",
        "options": ["0-1 years", "1-3 years", "3-5 years", "5+ years"],
    }
    open_ended = {**question, "options": ["0-1 years", "2-4 years", "5+ years"]}
    assert answer(tmp_path, question, {"total_experience": "2 years"}) == "1-3 years"
    assert answer(tmp_path, open_ended, {"total_experience": "2 years"}) == "2-4 years"


def test_income_expectations_use_the_expected_ctc(tmp_path):
    question = {"question": "Income Expectations", "field_type": "text"}
    assert answer(tmp_path, question, {"expected_ctc": "6 lpa"}) == "600000"


def test_conflict_of_interest_questions_answer_no(tmp_path):
    intellectual_property = {
        "question": "Intellectual Property: Do you own or have any interest in intellectual property?",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    outside_employment = {
        "question": "Outside Employment: Do you have any outside employment?",
        "field_type": "text",
    }
    board = {
        "question": "Board Memberships: Are you involved or seated on any board?",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    assert answer(tmp_path, intellectual_property) == "No"
    assert answer(tmp_path, outside_employment) == "No"
    assert answer(tmp_path, board) == "No"


def test_unrecorded_credentials_answer_no(tmp_path):
    passport = {
        "question": "Do you hold a valid passport?*",
        "field_type": "text",
        "options": ["Yes", "No"],
    }
    licence = {
        "question": "Do you have a valid driver's license?",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    clearance = {
        "question": "Do you hold an active security clearance?",
        "field_type": "dropdown",
        "options": ["Yes", "No"],
    }
    assert answer(tmp_path, passport) == "No"
    assert answer(tmp_path, licence) == "No"
    assert answer(tmp_path, clearance) == "No"


def test_international_travel_is_not_claimed_without_a_passport(tmp_path):
    international = {
        "question": "Are you willing to travel internationally to customer locations?*",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    domestic = {
        "question": "Are you willing to travel to customer locations?*",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    assert answer(tmp_path, international) == "No"
    assert answer(tmp_path, domestic) == "Yes"


def test_conditional_followups_answer_not_applicable(tmp_path):
    conditional_no = {
        "question": 'If you have answered "no" to the previous question, please provide details below.',
        "field_type": "text",
    }
    conditional_yes = {
        "question": "If you answered 'yes' above, please provide details",
        "field_type": "text",
    }
    choice = {
        **conditional_no,
        "field_type": "dropdown",
        "options": ["N/A", "Yes", "No"],
    }
    plain_choice = {**choice, "options": ["Yes", "No"]}
    assert answer(tmp_path, conditional_no) == "N/A"
    assert answer(tmp_path, conditional_yes) == "N/A"
    assert answer(tmp_path, choice) == "N/A"
    assert answer(tmp_path, plain_choice) == "No"
    settings = Settings(project_root=tmp_path, profile={})
    assert numeric_answer(conditional_no, settings, candidate()) == ""
    assert needs_numeric(conditional_no) is False


def test_referral_and_manager_followups_answer_not_applicable(tmp_path):
    referrer = {
        "question": "If you were referred by a current employee, please provide their name.",
        "field_type": "text",
    }
    who = {"question": "Who referred you to this role?", "field_type": "text"}
    manager = {
        "question": "What is the name of your current manager?",
        "field_type": "text",
    }
    for question in (referrer, who, manager):
        assert answer(tmp_path, question) == "N/A"


def test_direct_referral_questions_answer_no(tmp_path):
    question = {
        "question": "Were you referred by a current employee?",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    assert answer(tmp_path, question) == "No"


def test_serving_notice_followup_is_not_zero(tmp_path):
    question = {
        "question": "If you are serving notice, what will be your notice period?",
        "field_type": "text",
    }
    assert answer(tmp_path, question) == "N/A"
    settings = Settings(project_root=tmp_path, profile={"notice_period": "Immediate"})
    assert numeric_answer(question, settings, candidate()) == ""
    assert needs_numeric(question) is False

    serving = Settings(project_root=tmp_path, profile={"notice_period": "30 days"})
    assert answer(tmp_path, question, {"notice_period": "30 days"}) == "30"
    assert numeric_answer(question, serving, candidate()) == "30"


def test_email_and_country_code_choices_use_saved_contacts(tmp_path):
    email = {
        "question": "Email address*",
        "field_type": "dropdown",
        "options": ["candidate@example.com (Primary)", "other@example.com"],
    }
    code = {
        "question": "Phone country code*",
        "field_type": "dropdown",
        "options": ["+44 United Kingdom", "+91 India"],
    }
    profile = {"email": "candidate@example.com"}
    contact = replace(candidate(), phone="+91 9921626877")
    settings = Settings(project_root=tmp_path, profile=profile)
    assert answer(tmp_path, email, profile) == "candidate@example.com (Primary)"
    assert positive_answer(code, settings, contact, job()) == "+91 India"


def test_lone_skill_checkbox_is_not_checked_without_evidence(tmp_path):
    azure = {
        "question": "Experience with Azure cloud services?*",
        "field_type": "checkbox",
        "options": [],
    }
    consent = {
        "question": "You declare that you have read and agree to the privacy notice.*",
        "field_type": "checkbox",
        "options": [],
    }
    assert answer(tmp_path, azure) == "No"
    assert answer(tmp_path, consent) == "Yes"


def test_current_residence_questions_use_the_saved_city(tmp_path):
    bengaluru = {
        "question": "Are you currently residing in bengaluru?",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    india = {
        "question": "Are you currently based in India?*",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    pune = {"question": "Are you currently residing in Pune?", "field_type": "text"}
    profile = {"current_city": "Pune", "current_country": "India"}
    assert answer(tmp_path, bengaluru, profile) == "No"
    assert answer(tmp_path, india, profile) == "Yes"
    assert answer(tmp_path, pune, profile) == "Yes"


def test_work_authorization_is_limited_to_the_saved_country(tmp_path):
    uk = {
        "question": "Do you currently have full right to work in the United Kingdom?",
        "field_type": "text",
    }
    india = {
        "question": "Do you currently have full right to work in India?",
        "field_type": "text",
    }
    profile = {"current_country": "India"}
    assert answer(tmp_path, uk, profile) == "No"
    assert answer(tmp_path, india, profile) == "Yes"


def test_certifications_come_from_the_resume(tmp_path):
    certified = replace(candidate(), certifications=["Oracle Java Foundations"])
    question = {"question": "Have you completed any relevant certifications?", "field_type": "text"}
    choice = {**question, "field_type": "radio", "options": ["Yes", "No"]}
    settings = Settings(project_root=tmp_path, profile={})
    assert positive_answer(question, settings, certified, job()) == "Oracle Java Foundations"
    assert positive_answer(choice, settings, certified, job()) == "Yes"
    assert answer(tmp_path, question) == "No"
    assert answer(tmp_path, choice) == "No"


def test_supported_skill_claims_are_yes_not_prose(tmp_path):
    unit_testing = {
        "question": "Experience with unit testing and integration testing",
        "field_type": "text",
    }
    aws = {
        "question": "Do you have hands-on experience with AWS?",
        "field_type": "radio",
        "options": ["Yes", "No"],
    }
    aem = {"question": "Have you worked on AEM architecture and development?", "field_type": "text"}
    testing_candidate = replace(
        candidate(),
        skills=[*candidate().skills, "Unit Testing", "Integration Testing", "AWS"],
    )
    llm_candidate = replace(candidate(), skills=[*candidate().skills, "AI/LLM Tooling"])
    llm = {"question": "Have you worked on GenAI/LLM integration?", "field_type": "text"}
    settings = Settings(project_root=tmp_path, profile={})
    assert positive_answer(unit_testing, settings, testing_candidate, job()) == "Yes"
    assert positive_answer(aws, settings, testing_candidate, job()) == "Yes"
    assert answer(tmp_path, aem) == "No"
    assert positive_answer(llm, settings, llm_candidate, job()) == "Yes"


def test_dotnet_experience_is_supported_by_the_dotnet_stack(tmp_path):
    net_candidate = replace(candidate(), skills=[*candidate().skills, ".NET Stack"])
    question = {
        "question": "How many years of experience with .NET Core?",
        "field_type": "text",
    }
    settings = Settings(project_root=tmp_path, profile={"total_experience": "2 years"})
    assert positive_answer(question, settings, net_candidate, job()) == "2"


def test_optional_anything_else_prompt_is_not_answered_yes(tmp_path):
    question = {"question": "Is there anything else you’d like us to know?", "field_type": "text"}
    assert answer(tmp_path, question) == "N/A"


def test_yes_no_question_after_a_statement_still_gets_a_yes(tmp_path):
    question = {
        "question": "This is a contractual position. Are you comfortable with it?",
        "field_type": "text",
    }
    assert answer(tmp_path, question) == "Yes"
