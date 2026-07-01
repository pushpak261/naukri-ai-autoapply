"""Additional tests for employer metadata extraction."""

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.utils.job_metadata import apply_api_metadata, merge_job_metadata


def _job(**overrides):
    defaults = {
        "naukri_job_id": "123",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "url": "https://www.naukri.com/job-listings-123",
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_apply_api_metadata_sets_employer_fields():
    job = _job()
    apply_api_metadata(
        job,
        {
            "consultant": True,
            "companyDetail": {"hiringFor": "Flipkart"},
        },
    )
    assert job.is_consultant_post is True
    assert job.hiring_for == "Flipkart"


def test_merge_job_metadata_employer_fields():
    job = _job()
    merge_job_metadata(
        job,
        rating=None,
        verified=None,
        hiring_for="Amazon",
        is_consultant_post=False,
    )
    assert job.hiring_for == "Amazon"
    assert job.is_consultant_post is False
