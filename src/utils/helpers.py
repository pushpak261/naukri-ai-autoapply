"""
Shared utility functions for the Naukri Agent.

Includes random delay generation, text cleaning, async retry decorator,
file hashing, and other common helpers.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
from pathlib import Path
from typing import TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Delay / Timing utilities
# ---------------------------------------------------------------------------
async def random_delay(min_seconds: float, max_seconds: float) -> float:
    """
    Async sleep for a random duration (gaussian distribution clamped to range).

    Uses a gaussian distribution centered at the midpoint for more natural
    timing patterns, avoiding perfectly uniform randomness that looks robotic.

    Args:
        min_seconds: Minimum delay in seconds.
        max_seconds: Maximum delay in seconds.

    Returns:
        The actual number of seconds slept.
    """
    mean = (min_seconds + max_seconds) / 2
    std_dev = (max_seconds - min_seconds) / 4
    delay = random.gauss(mean, std_dev)
    delay = max(min_seconds, min(max_seconds, delay))  # Clamp
    await asyncio.sleep(delay)
    return delay


# ---------------------------------------------------------------------------
# Text cleaning utilities
# ---------------------------------------------------------------------------
def clean_text(text: str) -> str:
    """
    Clean raw text by removing HTML tags, normalizing whitespace, and
    stripping control characters.

    Args:
        text: Raw text (possibly with HTML).

    Returns:
        Cleaned text string.
    """
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove HTML entities
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(text: str, max_length: int = 4000) -> str:
    """
    Safely truncate text to a maximum length, preserving word boundaries.

    Args:
        text: Text to truncate.
        max_length: Maximum character count.

    Returns:
        Truncated text, with "..." appended if truncated.
    """
    if not text or len(text) <= max_length:
        return text
    truncated = text[:max_length]
    # Try to break at last space
    last_space = truncated.rfind(" ")
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]
    return truncated + "..."


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------
def hash_file(file_path: str | Path) -> str:
    """
    Compute SHA-256 hash of a file for caching/dedup purposes.

    Args:
        file_path: Path to the file.

    Returns:
        Hex string of the SHA-256 hash.
    """
    sha256 = hashlib.sha256()
    path = Path(file_path)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# URL / ID extraction
# ---------------------------------------------------------------------------
def extract_naukri_job_id(url: str) -> str:
    """
    Extract the Naukri job ID from a job URL.

    Naukri job URLs typically look like:
        https://www.naukri.com/job-listings-.../some-title-company-jobid-123456789

    The job ID is usually the numeric suffix or a unique identifier in the URL path.

    Args:
        url: Full Naukri job URL.

    Returns:
        Extracted job ID string, or a hash of the URL if extraction fails.
    """
    if not url:
        return hashlib.md5(b"unknown").hexdigest()[:16]

    # Try to extract numeric job ID from URL
    # Pattern: last numeric segment in the URL path
    match = re.search(r"-(\d{8,})(?:\?|$|&)", url)
    if match:
        return match.group(1)

    # Try jobid parameter
    match = re.search(r"[?&]jid=(\d+)", url)
    if match:
        return match.group(1)

    # Fallback: hash the URL path
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return hashlib.md5(parsed.path.encode()).hexdigest()[:16]


def build_search_url(
    keywords: str,
    location: str = "",
    experience_min: int = 0,
    experience_max: int = 50,
    salary_min: int = 0,
    freshness: int = 7,
    sort_by: str = "relevance",
    page: int = 1,
) -> str:
    """
    Build a Naukri.com job search URL from parameters.

    Args:
        keywords: Search keywords (e.g., "Python Developer").
        location: Location filter (e.g., "Bangalore").
        experience_min: Minimum experience in years.
        experience_max: Maximum experience in years.
        salary_min: Minimum salary filter.
        freshness: Job age in days.
        sort_by: Sort order ("relevance" or "date").
        page: Page number (1-indexed).

    Returns:
        Complete search URL string.
    """
    from urllib.parse import quote_plus

    # Build the slug (keywords hyphenated)
    slug = keywords.lower().replace(" ", "-")
    base_url = f"https://www.naukri.com/{slug}-jobs"

    params = []

    # Keywords
    params.append(f"k={quote_plus(keywords)}")

    # Location
    if location:
        params.append(f"l={quote_plus(location)}")

    # Experience range
    params.append(f"experience={experience_min}")
    if experience_max < 50:
        params.append(f"experiencemax={experience_max}")

    # Salary
    if salary_min > 0:
        params.append(f"salary={salary_min}")

    # Freshness
    if freshness:
        params.append(f"jobAge={freshness}")

    # Sort
    if sort_by == "date":
        params.append("sort=r")

    # Pagination
    if page > 1:
        params.append(f"pageNo={page}")

    # Source param (mimics natural navigation)
    params.append("nignbevent_src=jobsearchDeskGNB")

    query_string = "&".join(params)
    return f"{base_url}?{query_string}"
