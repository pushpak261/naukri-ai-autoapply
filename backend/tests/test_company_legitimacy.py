"""Tests for consultancy/recruiter employer legitimacy filtering."""

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.utils.company_legitimacy import (
    CompanyWebVerifier,
    EmployerLegitimacyFilter,
    company_matches_allowlist,
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


def test_consultant_without_hiring_company_is_rejected():
    filt = EmployerLegitimacyFilter(
        big_companies=["Infosys"],
        verify_online=False,
    )
    job = _job(company="Infosys", is_consultant_post=True, hiring_for=None)
    passes, reason = filt.evaluate_sync(job)
    assert passes is False
    assert "consultant" in reason.lower()


def test_recruiter_name_without_client_is_rejected():
    filt = EmployerLegitimacyFilter(verify_online=False)
    job = _job(company="ABC Staffing Solutions")
    passes, reason = filt.evaluate_sync(job)
    assert passes is False
    assert "recruiter" in reason.lower() or "staffing" in reason.lower()


def test_recruiter_with_named_client_passes_sync_checks():
    filt = EmployerLegitimacyFilter(
        big_companies=["Google"],
        verify_online=False,
    )
    job = _job(company="ABC Staffing Solutions", hiring_for="Google")
    passes, reason = filt.evaluate_sync(job)
    assert passes is True
    assert reason == ""


def test_allowlisted_direct_employer_passes():
    filt = EmployerLegitimacyFilter(
        big_companies=["Infosys", "Microsoft"],
        verify_online=False,
    )
    job = _job(company="Infosys Limited")
    passes, _ = filt.evaluate_sync(job)
    assert passes is True
    assert company_matches_allowlist("Infosys Limited", ["Infosys"])


async def test_allowlisted_company_skips_web_verification():
    verifier = CompanyWebVerifier()
    filt = EmployerLegitimacyFilter(
        big_companies=["Microsoft"],
        verify_online=True,
        web_verifier=verifier,
    )
    job = _job(company="Microsoft")
    passes, reason = await filt.evaluate(job)
    assert passes is True
    assert reason == ""


async def test_web_verifier_caches_results(monkeypatch):
    verifier = CompanyWebVerifier()

    async def fake_verify(company: str, *, allowlisted: bool = False):
        return True, "ok"

    monkeypatch.setattr(verifier, "verify_software_employer", fake_verify)
    first = await verifier.verify_software_employer("Acme Corp")
    second = await verifier.verify_software_employer("Acme Corp")
    assert first == second
