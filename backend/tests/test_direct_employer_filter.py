"""Tests for direct employer filtering."""

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.utils.company_legitimacy import DirectEmployerFilter
from src.naukri_agent.utils.job_metadata import merge_job_metadata


def _job(**overrides):
    defaults = {
        "naukri_job_id": "123",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "url": "https://www.naukri.com/job-listings-123",
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_direct_employer_with_name_logo_and_rating_passes():
    filt = DirectEmployerFilter()
    job = _job(
        company="Infosys Limited",
        has_company_logo=True,
        is_consultant_post=False,
        company_rating=4.2,
        is_verified=True,
    )
    passes, reason = filt.evaluate(job)
    assert passes is True
    assert reason == ""


def test_consultant_post_rejected_even_with_logo():
    filt = DirectEmployerFilter()
    job = _job(
        company="Infosys",
        has_company_logo=True,
        is_consultant_post=True,
        hiring_for="Google",
    )
    passes, reason = filt.evaluate(job)
    assert passes is False
    assert "consultancy" in reason.lower() or "recruiter" in reason.lower()


def test_recruiter_without_logo_rejected():
    filt = DirectEmployerFilter()
    job = _job(company="ABC Staffing Solutions", has_company_logo=False)
    passes, reason = filt.evaluate(job)
    assert passes is False


def test_tcs_direct_employer_with_logo_passes():
    filt = DirectEmployerFilter()
    job = _job(
        company="Tata Consultancy Services",
        has_company_logo=True,
        is_consultant_post=False,
    )
    passes, reason = filt.evaluate(job)
    assert passes is True
    assert reason == ""


def test_missing_company_name_rejected():
    filt = DirectEmployerFilter()
    job = _job(company="Not Disclosed", has_company_logo=True)
    passes, reason = filt.evaluate(job)
    assert passes is False
    assert "company name" in reason.lower()


def test_no_logo_rejected():
    filt = DirectEmployerFilter()
    job = _job(company="Acme Corp", has_company_logo=False, is_consultant_post=False)
    passes, reason = filt.evaluate(job)
    assert passes is False
    assert "logo" in reason.lower()


def test_unknown_logo_passes_with_strong_signals():
    filt = DirectEmployerFilter()
    job = _job(
        company="Acme Corp",
        has_company_logo=None,
        is_consultant_post=False,
        company_rating=4.0,
        is_verified=True,
    )
    passes, reason = filt.evaluate(job)
    assert passes is True
    assert reason == ""


def test_filter_disabled_passes_all():
    filt = DirectEmployerFilter(require_direct_employer=False)
    job = _job(company="Not Disclosed", is_consultant_post=True)
    passes, reason = filt.evaluate(job)
    assert passes is True
    assert reason == ""


def test_merge_job_metadata_logo_field():
    job = _job()
    merge_job_metadata(
        job,
        rating=4.0,
        verified=True,
        has_company_logo=True,
    )
    assert job.company_rating == 4.0
    assert job.is_verified is True
    assert job.has_company_logo is True
