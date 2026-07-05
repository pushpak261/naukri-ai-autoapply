"""Tests for consultancy/recruiter employer legitimacy filtering."""

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.utils.company_legitimacy import (
    CompanyWebVerifier,
    DirectEmployerFilter,
    EmployerLegitimacyFilter,
)
from src.naukri_agent.utils.job_metadata import (
    extract_hiring_for_from_api,
    extract_is_consultant_from_api,
)


def _job(**overrides):
    defaults = {
        "naukri_job_id": "123",
        "title": "Software Engineer",
        "company": "Infosys",
        "url": "https://www.naukri.com/job-listings-123",
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_extract_consultant_and_hiring_for_from_api():
    api_job = {
        "consultant": True,
        "companyDetail": {"hiringFor": "Google"},
        "postedBy": "consultant",
    }
    assert extract_is_consultant_from_api(api_job) is True
    assert extract_hiring_for_from_api(api_job) == "Google"


def test_consultant_post_rejected_by_direct_employer_filter():
    filt = DirectEmployerFilter()
    job = _job(company="Infosys", is_consultant_post=True, hiring_for=None)
    passes, reason = filt.evaluate(job)
    assert passes is False
    assert "consultancy" in reason.lower() or "recruiter" in reason.lower()


def test_recruiter_name_rejected_by_direct_employer_filter():
    filt = DirectEmployerFilter()
    job = _job(company="ABC Staffing Solutions", has_company_logo=True)
    passes, reason = filt.evaluate(job)
    assert passes is False
    assert "recruiter" in reason.lower() or "staffing" in reason.lower()


def test_recruiter_with_named_client_rejected():
    filt = DirectEmployerFilter()
    job = _job(
        company="ABC Staffing Solutions",
        hiring_for="Google",
        has_company_logo=True,
        is_consultant_post=False,
    )
    passes, reason = filt.evaluate(job)
    assert passes is False
    assert "client" in reason.lower() or "recruiter" in reason.lower() or "consultancy" in reason.lower()


def test_direct_employer_with_logo_passes():
    filt = DirectEmployerFilter()
    job = _job(company="Infosys Limited", has_company_logo=True, is_consultant_post=False)
    passes, _ = filt.evaluate(job)
    assert passes is True


async def test_web_verifier_caches_results(monkeypatch):
    verifier = CompanyWebVerifier()

    async def fake_verify(company: str):
        return True, "ok"

    monkeypatch.setattr(verifier, "verify_software_employer", fake_verify)
    first = await verifier.verify_software_employer("Acme Corp")
    second = await verifier.verify_software_employer("Acme Corp")
    assert first == second


async def test_employer_filter_skips_when_verify_disabled():
    filt = EmployerLegitimacyFilter(verify_online=False)
    job = _job(company="Unknown Startup")
    passes, reason = await filt.evaluate(job)
    assert passes is True
    assert reason == ""
