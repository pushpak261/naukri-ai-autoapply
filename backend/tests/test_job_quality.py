"""Tests for verified-job and company-rating quality filters."""

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.utils.filters import JobQualityFilter
from src.naukri_agent.utils.job_metadata import (
    apply_api_metadata,
    extract_company_rating_from_api,
    extract_is_verified_from_api,
    parse_company_rating,
)


def _job(**overrides):
    defaults = {
        "naukri_job_id": "123",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "url": "https://www.naukri.com/job-listings-123",
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_parse_company_rating():
    assert parse_company_rating("3.9") == 3.9
    assert parse_company_rating(4) == 4.0
    assert parse_company_rating("") is None
    assert parse_company_rating("6.0") is None


def test_extract_company_rating_from_api():
    api_job = {
        "ambitionBoxData": {
            "AggregateRating": "4.1",
            "ReviewsCount": "1200",
        }
    }
    assert extract_company_rating_from_api(api_job) == 4.1


def test_extract_is_verified_from_api():
    assert extract_is_verified_from_api({"isVerifiedJob": True}) is True
    assert extract_is_verified_from_api({"tags": ["Premium", "Verified"]}) is True
    assert extract_is_verified_from_api({"companyName": "Acme"}) is None


def test_apply_api_metadata_merges_onto_job():
    job = _job()
    apply_api_metadata(
        job,
        {
            "ambitionBoxData": {"AggregateRating": "3.8"},
            "isVerifiedJob": True,
        },
    )
    assert job.company_rating == 3.8
    assert job.is_verified is True


def test_quality_filter_requires_verified_first():
    quality_filter = JobQualityFilter(require_verified=True, min_company_rating=3.0)

    unverified = _job(is_verified=False, company_rating=4.5)
    passes, reason = quality_filter.evaluate(unverified)
    assert passes is False
    assert "not verified" in reason.lower()

    verified_low = _job(is_verified=True, company_rating=2.9)
    passes, reason = quality_filter.evaluate(verified_low)
    assert passes is False
    assert "rating" in reason.lower()


def test_quality_filter_only_accepts_rating_at_or_above_threshold():
    quality_filter = JobQualityFilter(require_verified=True, min_company_rating=3.0)

    at_threshold = _job(is_verified=True, company_rating=3.0)
    passes, _ = quality_filter.evaluate(at_threshold)
    assert passes is True

    below_threshold = _job(is_verified=True, company_rating=2.9)
    passes, reason = quality_filter.evaluate(below_threshold)
    assert passes is False
    assert "rating" in reason.lower()

    above_threshold = _job(is_verified=True, company_rating=3.1)
    passes, reason = quality_filter.evaluate(above_threshold)
    assert passes is True
    assert reason == ""


def test_search_stage_filter_only_drops_known_bad_jobs():
    quality_filter = JobQualityFilter(require_verified=True, min_company_rating=3.0)

    assert quality_filter.should_include_at_search(_job(is_verified=None, company_rating=None))
    assert not quality_filter.should_include_at_search(_job(is_verified=False, company_rating=4.0))
    assert not quality_filter.should_include_at_search(_job(is_verified=True, company_rating=2.5))
