"""Tests for big-company allowlist filtering."""

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.core.domain.specifications import BigCompanyAllowlistSpecification
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


def test_big_company_allowlist_matches_substring():
    spec = BigCompanyAllowlistSpecification(["Infosys", "TCS"])
    assert spec.is_satisfied_by(_job(company="Infosys Limited"))
    assert spec.is_satisfied_by(_job(company="TCS"))
    assert not spec.is_satisfied_by(_job(company="Small Startup Pvt Ltd"))


def test_big_company_allowlist_empty_matches_nothing():
    spec = BigCompanyAllowlistSpecification([])
    assert not spec.is_satisfied_by(_job(company="Infosys"))


def test_merge_job_metadata_apply_fields():
    job = _job()
    merge_job_metadata(
        job,
        rating=4.0,
        verified=True,
        is_external_apply=True,
        external_apply_url="https://careers.example.com/apply",
    )
    assert job.company_rating == 4.0
    assert job.is_verified is True
    assert job.is_external_apply is True
    assert job.external_apply_url == "https://careers.example.com/apply"
