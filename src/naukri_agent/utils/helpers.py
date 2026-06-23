"""
Shared utility classes and functions for the Naukri Agent.
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

from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class TimeUtility:
    """Namespace for timing and delay utilities."""

    @staticmethod
    async def random_delay(min_seconds: float, max_seconds: float) -> float:
        """
        Async sleep for a random duration (gaussian distribution clamped to range).
        """
        mean = (min_seconds + max_seconds) / 2
        std_dev = (max_seconds - min_seconds) / 4
        delay = random.gauss(mean, std_dev)
        delay = max(min_seconds, min(max_seconds, delay))  # Clamp
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
                            f"Attempt {attempt} of {max_attempts} for '{func.__name__}' failed: {e}. "
                            f"Retrying in {current_delay:.2f} seconds..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor

            return cast(F, wrapper)

        return decorator


class NaukriURLUtility:
    """Namespace for generating and parsing Naukri URLs and IDs."""

    @staticmethod
    def extract_job_id(url: str) -> str:
        """Extract the Naukri job ID from a job URL."""
        if not url:
            return hashlib.md5(b"unknown").hexdigest()[:16]
        match = re.search(r"-(\d{8,})(?:\?|$|&)", url)
        if match:
            return match.group(1)
        match = re.search(r"[?&]jid=(\d+)", url)
        if match:
            return match.group(1)
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return hashlib.md5(parsed.path.encode()).hexdigest()[:16]

    @staticmethod
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
        """Build a Naukri.com job search URL from parameters."""
        from urllib.parse import quote_plus

        clean_k = re.sub(r"[^a-zA-Z0-9]+", " ", keywords)
        slug = "-".join(clean_k.lower().split())
        if location:
            clean_l = re.sub(r"[^a-zA-Z0-9]+", " ", location)
            loc_slug = "-".join(clean_l.lower().split())
            path = f"{slug}-jobs-in-{loc_slug}"
        else:
            path = f"{slug}-jobs"
        if page > 1:
            path = f"{path}-{page}"
        base_url = f"https://www.naukri.com/{path}"
        params = []
        params.append(f"k={quote_plus(keywords)}")
        if location:
            params.append(f"l={quote_plus(location)}")
        params.append(f"experience={experience_min}")
        if experience_max < 50:
            params.append(f"experiencemax={experience_max}")
        if salary_min > 0:
            params.append(f"salary={salary_min}")
        if freshness:
            params.append(f"jobAge={freshness}")
        if sort_by == "date":
            params.append("sort=r")
        if page > 1:
            params.append(f"pageNo={page}")
        params.append("nignbevent_src=jobsearchDeskGNB")
        query_string = "&".join(params)
        return f"{base_url}?{query_string}"


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


def async_retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    return RetryUtility.async_retry(max_attempts, delay_seconds, backoff_factor, exceptions)


def extract_naukri_job_id(url: str) -> str:
    return NaukriURLUtility.extract_job_id(url)


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
    return NaukriURLUtility.build_search_url(
        keywords, location, experience_min, experience_max, salary_min, freshness, sort_by, page
    )
