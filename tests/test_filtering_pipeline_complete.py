"""
Comprehensive test suite for the entire job filtering pipeline.

Tests individual filters and composite evaluation on real-world job samples
(including scam jobs, consultancy jobs, non-matching roles, experience limits,
company blacklists, description blacklists, and duplicate jobs).
"""

import pytest
from src.naukri_agent.config.settings import Settings, ExclusionSettings, SearchSettings, ApplicationSettings
from src.naukri_agent.models.entities import Job
from src.naukri_agent.fake_job_detection.rules import (
    compute_scam_score,
    is_job_in_excluded_domain,
    evaluate_job_all_filters,
)
from src.naukri_agent.fake_job_detection.pipeline import FakeJobDetectionPipeline
from src.naukri_agent.utils.filters import JobFilter


@pytest.fixture
def settings() -> Settings:
    s = Settings()
    s.exclusions = ExclusionSettings(
        enable_scam_filter=True,
        companies=["Techno Experts", "TeleInfoTech", "Orcapod Consulting Services", "Talentzo"],
        fake_company_blocklist=["Fake Company Ltd", "Spam Company 1"],
        max_openings_without_logo=25,
        title_keywords=[
            "consultant", "consultants", "sales", "marketing", "bpo", "telecaller",
            "walk-in", "walkin", "trainee", "diploma trainee", "training", "animator",
            "physiotherapist", "therapist", "safety database specialist", "care engineer",
            "payroll", "design engineer", "qa", "tester"
        ],
        description_keywords=["send your resume", "whatsapp your resume", "registration fee", "training charges"],
    )
    s.search = SearchSettings(
        experience_max=2,
        experience_min=0,
        freshness=30,
        enable_heuristics=True,
    )
    s.application = ApplicationSettings(
        match_score_threshold=40.0,
    )
    return s


# ======================================================================
# 1. Scam & Consultancy Detection Filter Tests
# ======================================================================

def test_partner_consultant_blocked_by_scam_and_title_filter(settings):
    job = Job(
        naukri_job_id="101",
        title="PARTNER CONSULTANT - Identity Management (LCM/RBAC)",
        company="Happiest Minds Technologies",
        experience="0 Yrs",
        url="https://example.com/job101",
    )

    res = compute_scam_score(job)
    assert res.raw_score >= 80, f"Expected scam score >= 80 for consultant title, got {res.raw_score}"

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert eval_res["filter_evaluations"]["scam_detection"]["passed"] is False
    assert eval_res["filter_evaluations"]["title_blacklist"]["passed"] is False


def test_walkin_diploma_trainee_blocked(settings):
    job = Job(
        naukri_job_id="102",
        title="Walk-in || Diploma Trainee",
        company="Adroitre Energy",
        posted_date="21 Jul - 25 Jul",
        url="https://example.com/job102",
    )

    res = compute_scam_score(job)
    assert res.raw_score >= 80, f"Expected walk-in to trigger scam score >= 80, got {res.raw_score}"

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert any("Walk-in" in r or "trainee" in r.lower() for r in eval_res["rejection_reasons"])


def test_php_training_professional_blocked(settings):
    job = Job(
        naukri_job_id="103",
        title="PHP Training professional",
        company="Sibz Solutions",
        experience="0-4 Yrs",
        url="https://example.com/job103",
    )

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert eval_res["filter_evaluations"]["title_blacklist"]["passed"] is False


# ======================================================================
# 2. Non-Matching / Domain Filter Tests
# ======================================================================

def test_physiotherapist_blocked(settings):
    job = Job(
        naukri_job_id="104",
        title="Physiotherapist",
        company="New Horizons Child Development Centre",
        experience="0-2 Yrs",
        url="https://example.com/job104",
    )

    is_excl, reason = is_job_in_excluded_domain(job)
    assert is_excl is True
    assert "Medical/Healthcare" in reason

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert eval_res["filter_evaluations"]["title_blacklist"]["passed"] is False


def test_safety_database_specialist_blocked(settings):
    job = Job(
        naukri_job_id="105",
        title="Safety Database Specialist",
        company="Medspace Clinical Research India",
        experience="0-2 Yrs",
        url="https://example.com/job105",
    )

    is_excl, reason = is_job_in_excluded_domain(job)
    assert is_excl is True

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert eval_res["filter_evaluations"]["title_blacklist"]["passed"] is False


def test_freelance_animator_blocked(settings):
    job = Job(
        naukri_job_id="106",
        title="Freelance Senior Animator",
        company="Outpost Vfx",
        experience="0-2 Yrs",
        url="https://example.com/job106",
    )

    is_excl, _ = is_job_in_excluded_domain(job)
    assert is_excl is True

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False


# ======================================================================
# 3. Experience Limit Filter Tests
# ======================================================================

def test_experience_limit_blocks_0_to_5_years_when_max_is_2(settings):
    job = Job(
        naukri_job_id="107",
        title="Product Designer",
        company="Legit Farms",
        experience="0-5 Yrs",
        url="https://example.com/job107",
    )

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["filter_evaluations"]["experience"]["passed"] is False
    assert "exceeds target limit" in eval_res["filter_evaluations"]["experience"]["reason"]

    jf = JobFilter(max_experience=2, max_freshness_days=30)
    filtered = jf.filter([job])
    assert len(filtered) == 0


def test_experience_limit_passes_0_to_2_years(settings):
    job = Job(
        naukri_job_id="108",
        title="Junior Backend Engineer",
        company="Acme Tech",
        experience="0-2 Yrs",
        url="https://example.com/job108",
    )

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["filter_evaluations"]["experience"]["passed"] is True


# ======================================================================
# 4. Company & Description Blacklist Tests
# ======================================================================

def test_blacklisted_company_blocked(settings):
    job = Job(
        naukri_job_id="109",
        title="Software Engineer",
        company="TeleInfoTech",
        url="https://example.com/job109",
    )

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert eval_res["filter_evaluations"]["company_blacklist"]["passed"] is False


def test_hidden_company_blocked(settings):
    job = Job(
        naukri_job_id="110",
        title="Software Developer",
        company="Confidential Client",
        url="https://example.com/job110",
    )

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert eval_res["filter_evaluations"]["company_blacklist"]["passed"] is False


def test_description_blacklist_blocked(settings):
    job = Job(
        naukri_job_id="111",
        title="Software Engineer",
        company="Valid Tech Ltd",
        description="Immediate joining required. Please send your resume to HR on whatsapp.",
        url="https://example.com/job111",
    )

    eval_res = evaluate_job_all_filters(job, settings)
    assert eval_res["passed"] is False
    assert eval_res["filter_evaluations"]["description_blacklist"]["passed"] is False


# ======================================================================
# 5. Genuine Job Test & Pipeline Integration
# ======================================================================

def test_genuine_software_engineer_passes_all_filters(settings):
    job = Job(
        naukri_job_id="112",
        title="Backend Software Engineer - Python",
        company="Flipkart",
        experience="0-2 Yrs",
        posted_date="1 day ago",
        has_company_logo=True,
        openings=2,
        description="We are looking for a Python Software Engineer with experience in Django, PostgreSQL, Docker, and REST APIs.",
        url="https://example.com/job112",
    )

    eval_res = evaluate_job_all_filters(job, settings, heuristic_score=0.25, match_score=75.0)
    assert eval_res["passed"] is True
    assert len(eval_res["rejection_reasons"]) == 0


def test_pipeline_deduplication(settings):
    job1 = Job(naukri_job_id="201", title="Backend Engineer", company="Stripe", url="https://example.com/201")
    job2 = Job(naukri_job_id="201", title="Backend Engineer", company="Stripe", url="https://example.com/201_dup")
    job3 = Job(naukri_job_id="202", title="Frontend Engineer", company="Vercel", url="https://example.com/202")

    unique, duplicates = FakeJobDetectionPipeline.deduplicate_jobs([job1, job2, job3])
    assert len(unique) == 2
    assert len(duplicates) == 1
    assert duplicates[0].naukri_job_id == "201"
