"""
Helpers for extracting Naukri job quality signals (verified badge, company rating).
"""

from __future__ import annotations

import re
from typing import Any

from src.naukri_agent.core.domain.entities import Job

_RATING_PATTERN = re.compile(r"(\d+(?:\.\d+)?)")


def parse_company_rating(value: Any) -> float | None:
    """Parse a company rating value from API/DOM text."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        rating = float(value)
        return rating if 0 < rating <= 5 else None
    text = str(value).strip()
    if not text:
        return None
    match = _RATING_PATTERN.search(text)
    if not match:
        return None
    rating = float(match.group(1))
    return rating if 0 < rating <= 5 else None


def extract_company_rating_from_api(api_job: dict[str, Any]) -> float | None:
    """Read AmbitionBox / company rating from a Naukri search/detail API payload."""
    for box_key in ("ambitionBoxData", "ambition_box_data", "ambitionBoxDetails"):
        box = api_job.get(box_key)
        if not isinstance(box, dict):
            continue
        for rating_key in (
            "AggregateRating",
            "aggregate_rating",
            "overallRating",
            "overall_rating",
        ):
            rating = parse_company_rating(box.get(rating_key))
            if rating is not None:
                return rating

    for rating_key in ("companyRating", "company_rating"):
        rating = parse_company_rating(api_job.get(rating_key))
        if rating is not None:
            return rating

    branding = api_job.get("jdBrandingDetails")
    if isinstance(branding, dict):
        rating = parse_company_rating(branding.get("overallRating"))
        if rating is not None:
            return rating

    return None


def extract_is_verified_from_api(api_job: dict[str, Any]) -> bool | None:
    """
    Read verified-job status from a Naukri API payload.

    Returns True/False when the API exposes an explicit flag, otherwise None.
    """
    for key in (
        "isVerified",
        "isVerifiedJob",
        "verified",
        "jdVerified",
        "isVerifiedEmployer",
        "verifiedJob",
    ):
        if key not in api_job:
            continue
        value = api_job[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False

    for tags_key in ("tags", "tagLabels", "jobTags"):
        tags = api_job.get(tags_key)
        if isinstance(tags, list) and any("verified" in str(tag).lower() for tag in tags):
            return True

    footer = str(api_job.get("footerPlaceholderLabel", "")).lower()
    if re.search(r"\bverified\b", footer):
        return True

    return None


def _parse_bool_flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "y"}:
            return True
        if lowered in {"false", "no", "0", "n"}:
            return False
    return None


def extract_hiring_for_from_api(api_job: dict[str, Any]) -> str | None:
    """Read end-client / hiring-for label from a Naukri API payload."""
    for key in ("hiringFor", "hiring_for", "clientName", "client_name", "endClient"):
        label = _clean_label_from_api(api_job.get(key))
        if label:
            return label

    company_detail = api_job.get("companyDetail")
    if isinstance(company_detail, dict):
        for key in ("hiringFor", "hiring_for", "clientName", "name"):
            label = _clean_label_from_api(company_detail.get(key))
            if label:
                return label

    branding = api_job.get("jdBrandingDetails")
    if isinstance(branding, dict):
        for key in ("hiringFor", "clientName"):
            label = _clean_label_from_api(branding.get(key))
            if label:
                return label

    return None


def extract_is_consultant_from_api(api_job: dict[str, Any]) -> bool | None:
    """Read consultant/recruiter post flag from a Naukri API payload."""
    for key in (
        "consultant",
        "isConsultant",
        "is_consultant",
        "consultantJob",
        "postedByConsultant",
    ):
        flag = _parse_bool_flag(api_job.get(key))
        if flag is not None:
            return flag

    posted_by = str(api_job.get("postedBy", "")).strip().lower()
    if posted_by == "consultant":
        return True
    if posted_by == "company":
        return False

    group_type = str(api_job.get("groupType", "")).strip().lower()
    if "consult" in group_type:
        return True

    company_detail = api_job.get("companyDetail")
    if isinstance(company_detail, dict):
        client_type = str(company_detail.get("clientType", "")).strip()
        hiring_for = company_detail.get("hiringFor")
        if client_type and hiring_for:
            return True
        consultant_flag = _parse_bool_flag(company_detail.get("consultant"))
        if consultant_flag is not None:
            return consultant_flag

    return None


def _clean_label_from_api(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"", "not disclosed", "confidential", "na", "n/a", "-", "hidden"}:
        return None
    return text


def apply_api_metadata(job: Job, api_job: dict[str, Any]) -> None:
    """Merge rating / verified / employer fields from an API job object onto a Job entity."""
    rating = extract_company_rating_from_api(api_job)
    if rating is not None:
        job.company_rating = rating

    verified = extract_is_verified_from_api(api_job)
    if verified is not None:
        job.is_verified = verified

    hiring_for = extract_hiring_for_from_api(api_job)
    if hiring_for and job.hiring_for is None:
        job.hiring_for = hiring_for

    consultant = extract_is_consultant_from_api(api_job)
    if consultant is not None and job.is_consultant_post is None:
        job.is_consultant_post = consultant


def parse_dom_metadata(raw: dict[str, Any]) -> tuple[float | None, bool | None]:
    """Parse company rating and verified flag from browser DOM extraction."""
    rating = parse_company_rating(raw.get("company_rating"))
    verified_raw = raw.get("is_verified")
    verified: bool | None
    if verified_raw is None:
        verified = None
    else:
        verified = bool(verified_raw)
    return rating, verified


def merge_job_metadata(
    job: Job,
    *,
    rating: float | None,
    verified: bool | None,
    is_external_apply: bool | None = None,
    external_apply_url: str | None = None,
    hiring_for: str | None = None,
    is_consultant_post: bool | None = None,
) -> None:
    """Fill missing Job metadata without overwriting known values."""
    if job.company_rating is None and rating is not None:
        job.company_rating = rating
    if job.is_verified is None and verified is not None:
        job.is_verified = verified
    if job.is_external_apply is None and is_external_apply is not None:
        job.is_external_apply = is_external_apply
    if job.external_apply_url is None and external_apply_url:
        job.external_apply_url = external_apply_url
    if job.hiring_for is None and hiring_for:
        job.hiring_for = hiring_for
    if job.is_consultant_post is None and is_consultant_post is not None:
        job.is_consultant_post = is_consultant_post
