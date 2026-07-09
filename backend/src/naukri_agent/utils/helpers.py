"""
Shared utility classes and functions for the Naukri Agent.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import random
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast, overload

from src.naukri_agent.utils.logger import get_logger

if TYPE_CHECKING:
    from src.naukri_agent.config.settings import Settings

CANONICAL_RESUME_REL_PATH = "data/resumes/resume.pdf"
CANONICAL_RESUME_NAME = "resume.pdf"

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
    def build_job_detail_url(
        *,
        url: str | None = None,
        naukri_job_id: str | None = None,
    ) -> str:
        """Resolve a navigable Naukri job detail URL from a listing URL or job id."""
        raw = (url or "").strip()
        if raw:
            if raw.startswith("http"):
                return raw
            return f"https://www.naukri.com{raw if raw.startswith('/') else '/' + raw}"

        job_id = (naukri_job_id or "").strip()
        if job_id.isdigit():
            return f"https://www.naukri.com/job-listings-{job_id}"
        return ""

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

        def _create_slug(text: str) -> str:
            if not text:
                return ""
            slug = text.lower().strip()
            # Mapping common programming/tech skills with special characters
            mappings = [
                (r"c/c\+\+(?!\w)", "c-c-plus-plus"),
                (r"c\+\+(?!\w)", "c-plus-plus"),
                (r"c#(?!\w)", "c-sharp"),
                (r"f#(?!\w)", "f-sharp"),
                (r"j#(?!\w)", "j-sharp"),
                (r"asp\.net(?!\w)", "asp-dot-net"),
                (r"\.net(?!\w)", "dot-net"),
                (r"pl/sql(?!\w)", "pl-sql"),
                (r"t-sql(?!\w)", "t-sql"),
                (r"no-sql(?!\w)", "no-sql"),
                (r"ui/ux(?!\w)", "ui-ux"),
                (r"html/css(?!\w)", "html-css"),
                (r"tcp/ip(?!\w)", "tcp-ip"),
                (r"react\.js(?!\w)", "react-js"),
                (r"node\.js(?!\w)", "node-js"),
                (r"vue\.js(?!\w)", "vue-js"),
                (r"angular\.js(?!\w)", "angular-js"),
                (r"next\.js(?!\w)", "next-js"),
                (r"nuxt\.js(?!\w)", "nuxt-js"),
                (r"nest\.js(?!\w)", "nest-js"),
                (r"three\.js(?!\w)", "three-js"),
                (r"d3\.js(?!\w)", "d3-js"),
                (r"backbone\.js(?!\w)", "backbone-js"),
                (r"ember\.js(?!\w)", "ember-js"),
            ]
            for pattern, replacement in mappings:
                slug = re.sub(pattern, replacement, slug)

            # Catch other generic *.js variants
            slug = re.sub(r"\b(\w+)\.js(?!\w)", r"\1-js", slug)
            # Replace remaining non-alphanumeric (except hyphens) with a space
            slug = re.sub(r"[^a-zA-Z0-9\-]+", " ", slug)
            return "-".join(slug.split())

        # Coerce types to prevent TypeErrors from dynamic config inputs
        try:
            experience_min = int(experience_min)
        except (ValueError, TypeError):
            experience_min = 0

        try:
            experience_max = int(experience_max)
        except (ValueError, TypeError):
            experience_max = 50

        try:
            salary_min = int(salary_min)
        except (ValueError, TypeError):
            salary_min = 0

        try:
            freshness = int(freshness) if freshness is not None else 7
        except (ValueError, TypeError):
            freshness = 7

        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1

        # Bound page number between 1 and 100 to prevent out-of-bounds routing
        bounded_page = max(1, min(100, page))

        slug = _create_slug(keywords)
        if location:
            loc_slug = _create_slug(location)
            path = f"{slug}-jobs-in-{loc_slug}" if slug else f"jobs-in-{loc_slug}"
        else:
            path = f"{slug}-jobs" if slug else "jobs"

        # Append page suffix directly to URL path slug for SEO/pagination router
        if bounded_page > 1:
            path = f"{path}-{bounded_page}"

        base_url = f"https://www.naukri.com/{path}"
        params = []

        # Explicitly append search keywords & location query parameters for backend reliability
        from urllib.parse import quote

        if keywords:
            params.append(f"k={quote(keywords)}")
        if location:
            params.append(f"l={quote(location)}")
        if bounded_page > 1:
            params.append(f"pageNo={bounded_page}")

        # Naukri's frontend has a bug where `experiencemax` is ignored in the UI slider.
        # We must ALWAYS pass `experience={experience_min}` to ensure the backend at least returns the correct minimum.
        # We also pass `experiencemax` just in case the backend respects it, even if the UI slider breaks.
        params.append(f"experience={experience_min}")

        if experience_max <= experience_min:
            experience_max = experience_min + 1

        if experience_max < 50:
            params.append(f"experiencemax={experience_max}")
        if salary_min > 0:
            params.append(f"salary={salary_min}")
        if freshness:
            params.append(f"jobAge={freshness}")
        if sort_by == "date":
            params.append("sort=d")
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


def resolve_resume_path(settings: Settings, *, sync: bool = True) -> Path | None:
    """
    Resolve the active resume PDF path.

    Prefers the canonical ``data/resumes/resume.pdf`` (under the backend project
    root, with a repo-root fallback). When a newer copy exists outside the
    backend tree, it is synced into the canonical location so parsing and
    uploads always target the same file.
    """
    canonical = settings.resumes_dir / CANONICAL_RESUME_NAME
    repo_root_resume = settings.project_root.parent / "data" / "resumes" / CANONICAL_RESUME_NAME

    candidates: list[Path] = []
    for path in (repo_root_resume, canonical):
        if path.exists():
            candidates.append(path.resolve())

    if not candidates:
        if settings.resume.path:
            configured = Path(settings.resume.path)
            if not configured.is_absolute():
                configured = settings.project_root / configured
            return configured.resolve() if configured.exists() else None
        return None

    active = max(candidates, key=lambda path: path.stat().st_mtime)

    if sync and active != canonical.resolve():
        settings.ensure_dirs()
        shutil.copy2(active, canonical)
        active = canonical.resolve()
        logger.info(f"Synced resume to canonical path: {canonical}")

    return active


def patch_settings_resume_path(settings: Settings) -> Path | None:
    """Resolve the active resume file and patch runtime settings to match."""
    path = resolve_resume_path(settings)
    if not path:
        return None

    try:
        rel = path.relative_to(settings.project_root)
        settings.resume.path = str(rel).replace("\\", "/")
    except ValueError:
        settings.resume.path = CANONICAL_RESUME_REL_PATH
    return path


def async_retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    return RetryUtility.async_retry(max_attempts, delay_seconds, backoff_factor, exceptions)


def extract_naukri_job_id(url: str) -> str:
    return NaukriURLUtility.extract_job_id(url)


def build_job_detail_url(
    *,
    url: str | None = None,
    naukri_job_id: str | None = None,
) -> str:
    return NaukriURLUtility.build_job_detail_url(url=url, naukri_job_id=naukri_job_id)


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
