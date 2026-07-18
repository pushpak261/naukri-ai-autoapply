"""
Shared utility classes and functions for the LinkedIn Agent.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import random
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast, overload

from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class TimeUtility:
    """Namespace for timing and delay utilities."""

    @staticmethod
    async def random_delay(min_seconds: float, max_seconds: float) -> float:
        """Async sleep for a random duration (gaussian distribution clamped to range)."""
        mean = (min_seconds + max_seconds) / 2
        std_dev = (max_seconds - min_seconds) / 4
        delay = random.gauss(mean, std_dev)
        delay = max(min_seconds, min(max_seconds, delay))
        await asyncio.sleep(delay)
        return delay


class TextUtility:
    """Namespace for formatting, cleaning, and truncating text."""

    @staticmethod
    def clean(text: str | None) -> str:
        """Clean raw text by removing HTML tags and normalizing whitespace."""
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-zA-Z]+;", " ", text)
        text = re.sub(r"&#\d+;", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    @overload
    def truncate(text: None, max_length: int = 4000) -> None: ...

    @staticmethod
    @overload
    def truncate(text: str, max_length: int = 4000) -> str: ...

    @staticmethod
    def truncate(text: str | None, max_length: int = 4000) -> str | None:
        """Safely truncate text to a maximum length, preserving word boundaries."""
        if not text or len(text) <= max_length:
            return text
        truncated = text[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:
            truncated = truncated[:last_space]
        return truncated + "..."


class CryptographicUtility:
    """Namespace for hashing and checksum algorithms."""

    @staticmethod
    def hash_file(file_path: str | Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        path = Path(file_path)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


F = TypeVar("F", bound=Callable[..., Any])


class RetryUtility:
    """Namespace for retry policies and execution wrapper decorators."""

    @staticmethod
    def async_retry(
        max_attempts: int = 3,
        delay_seconds: float = 1.0,
        backoff_factor: float = 2.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> Callable[[F], F]:
        """Decorator to retry an asynchronous function with exponential backoff."""

        def decorator(func: F) -> F:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                current_delay = delay_seconds
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        if getattr(e, "is_daily_quota", False):
                            raise
                        if attempt == max_attempts:
                            logger.error(
                                f"Function '{func.__name__}' failed after {max_attempts} attempts: {e}"
                            )
                            raise
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} for '{func.__name__}' failed: {e}. "
                            f"Retrying in {current_delay:.2f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor

            return cast(F, wrapper)

        return decorator


class LinkedInURLUtility:
    """Namespace for generating and parsing LinkedIn URLs and IDs."""

    @staticmethod
    def extract_job_id(url: str) -> str:
        """Extract the LinkedIn job ID from a job URL."""
        if not url:
            return hashlib.md5(b"unknown").hexdigest()[:16]

        # LinkedIn job IDs are typically numeric in the URL path
        # Pattern: /jobs/view/1234567890
        match = re.search(r"/jobs/view/(\d+)", url)
        if match:
            return match.group(1)

        # Pattern: ?currentJobId=1234567890
        match = re.search(r"currentJobId=(\d+)", url)
        if match:
            return match.group(1)

        # Pattern: /jobs/search/... with job reference
        match = re.search(r"jobPosting/(\d+)", url)
        if match:
            return match.group(1)

        # Fallback: hash the URL path
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return hashlib.md5(parsed.path.encode()).hexdigest()[:16]

    @staticmethod
    def extract_company_from_url(url: str) -> str:
        """Try to extract company slug from LinkedIn URL."""
        match = re.search(r"/company/([^/]+)", url)
        if match:
            return match.group(1).replace("-", " ").title()
        return ""

    @staticmethod
    def build_search_url(
        keywords: str,
        location: str = "",
        freshness: str = "604800",
        experience: str = "",
        job_type: str = "",
        sort_by: str = "relevance",
        start: int = 0,
        work_type: str = "",
        easy_apply_only: bool = False,
    ) -> str:
        """Build a LinkedIn job search URL from parameters."""
        base_url = "https://www.linkedin.com/jobs/search/"
        params = []

        if keywords:
            from urllib.parse import quote
            params.append(f"keywords={quote(keywords)}")
        if location:
            from urllib.parse import quote
            params.append(f"location={quote(location)}")
        if freshness:
            params.append(f"f_TPR={freshness}")
        if experience:
            params.append(f"f_E={experience}")
        if job_type:
            params.append(f"f_JT={job_type}")
        if sort_by in ("date", "DD"):
            params.append("sortBy=DD")
        if start > 0:
            params.append(f"start={start}")
        if work_type:
            params.append(f"f_WT={work_type}")

        # Only filter for Easy Apply jobs if specifically configured
        if easy_apply_only:
            params.append("f_AL=true")

        query_string = "&".join(params)
        return f"{base_url}?{query_string}" if query_string else base_url


# ---------------------------------------------------------------------------
# Backward-compatibility deprecated module-level wrappers
# ---------------------------------------------------------------------------
async def random_delay(min_seconds: float, max_seconds: float) -> float:
    return await TimeUtility.random_delay(min_seconds, max_seconds)


def clean_text(text: str | None) -> str:
    return TextUtility.clean(text)


@overload
def truncate_text(text: None, max_length: int = 4000) -> None: ...


@overload
def truncate_text(text: str, max_length: int = 4000) -> str: ...


def truncate_text(text: str | None, max_length: int = 4000) -> str | None:
    return TextUtility.truncate(text, max_length)


def hash_file(file_path: str | Path) -> str:
    return CryptographicUtility.hash_file(file_path)


def extract_linkedin_job_id(url: str) -> str:
    return LinkedInURLUtility.extract_job_id(url)


def build_search_url(
    keywords: str,
    location: str = "",
    freshness: str = "604800",
    experience: str = "",
    job_type: str = "",
    sort_by: str = "relevance",
    start: int = 0,
    work_type: str = "",
) -> str:
    return LinkedInURLUtility.build_search_url(
        keywords, location, freshness, experience, job_type, sort_by, start, work_type
    )
