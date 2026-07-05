"""Tests for company logo metadata extraction."""

from src.naukri_agent.utils.job_metadata import (
    extract_has_company_logo_from_api,
    parse_dom_logo_flag,
)


def test_extract_logo_from_company_detail():
    api_job = {
        "companyDetail": {"logo": "https://img.naukimg.com/logo/v1/infosys.png"},
    }
    assert extract_has_company_logo_from_api(api_job) is True


def test_extract_logo_from_top_level_key():
    api_job = {"companyLogo": "https://cdn.example.com/acme-logo.jpg"}
    assert extract_has_company_logo_from_api(api_job) is True


def test_placeholder_logo_returns_none():
    api_job = {"companyLogo": "https://cdn.example.com/default-placeholder.png"}
    assert extract_has_company_logo_from_api(api_job) is None


def test_missing_logo_returns_none():
    api_job = {"companyName": "Acme Corp"}
    assert extract_has_company_logo_from_api(api_job) is None


def test_parse_dom_logo_flag():
    assert parse_dom_logo_flag(True) is True
    assert parse_dom_logo_flag(False) is False
    assert parse_dom_logo_flag(None) is None
