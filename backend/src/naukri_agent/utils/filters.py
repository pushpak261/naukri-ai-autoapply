"""
Job filtering utilities.

Separates the business logic of filtering jobs by various criteria
(e.g., experience, freshness) from the scraping orchestration to increase modularity.
"""

from __future__ import annotations

import re
import logging
from src.naukri_agent.models.entities import Job

logger = logging.getLogger(__name__)


class JobFilter:
    """
    Applies strict client-side filtering on parsed job cards to bypass
    Naukri's ignored URL params or incorrect search results.
    """

    def __init__(
        self,
        max_experience: int,
        max_freshness_days: int,
        sort_by: str = "relevance",
        min_experience: int = 0,
    ) -> None:
        self.min_experience = min_experience
        self.max_experience = max_experience
        self.max_freshness_days = max_freshness_days
        self.sort_by = sort_by

    def filter(self, jobs: list[Job]) -> list[Job]:
        """
        Filter a list of jobs based on initialized constraints.

        Args:
            jobs: List of parsed Job entities.

        Returns:
            List of Job entities that pass all filter criteria, optionally sorted.
        """
        filtered_jobs = []

        for job in jobs:
            if self._passes_experience_filter(
                str(job.experience)
            ) and self._passes_freshness_filter(str(job.posted_date)):
                filtered_jobs.append(job)
            else:
                logger.info(
                    f"Local filter removed: {job.title} "
                    f"(Exp: '{job.experience}', Age: '{job.posted_date}')"
                )

        if self.sort_by == "date":
            filtered_jobs.sort(key=lambda j: self._parse_date_to_days(str(j.posted_date)))

        return filtered_jobs

    def _passes_experience_filter(self, exp_text: str) -> bool:
        """Check if user and job experience ranges overlap."""
        parsed = parse_experience_range(exp_text)
        if parsed is None:
            return True
        job_min, job_max = parsed
        return ranges_overlap(job_min, job_max, self.min_experience, self.max_experience)

    def _passes_freshness_filter(self, date_text: str) -> bool:
        """Check if the job posting age is within limits."""
        if self.max_freshness_days <= 0:
            return True

        days = self._parse_date_to_days(date_text)
        return days <= self.max_freshness_days

    @staticmethod
    def _parse_date_to_days(date_text: str) -> int:
        """Convert a job posting date string to an approximate number of days."""
        parsed = parse_posted_age_days(date_text)
        return parsed if parsed is not None else 999


def ranges_overlap(job_min: int, job_max: int, user_min: int, user_max: int) -> bool:
    """Return whether job and user experience ranges overlap."""
    return job_min <= user_max and job_max >= user_min


def parse_experience_range(exp_text: str) -> tuple[int, int] | None:
    """
    Parse job experience text into a numeric min/max range.

    Supports inputs like "0-2 Yrs", "3 to 5 years", and "3 Yrs".
    Returns None when parsing is unreliable.
    """
    text = str(exp_text or "").strip().lower()
    if not text:
        return None

    months = {
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    }
    if any(month in text for month in months):
        return None

    range_match = re.search(r"(\d+)\s*(?:-|–|to)\s*(\d+)", text)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        return (min(low, high), max(low, high))

    single_match = re.search(r"(\d+)", text)
    if single_match:
        value = int(single_match.group(1))
        return (value, value)
    return None


def parse_posted_age_days(date_text: str) -> int | None:
    """Parse relative posted-date text into age in days."""
    text = str(date_text or "").strip().lower()
    if not text:
        return None
    if (
        "just now" in text
        or "today" in text
        or "hour" in text
        or "minute" in text
        or "second" in text
    ):
        return 0
    if "yesterday" in text:
        return 1
    if "30+" in text:
        return 31

    if "week" in text:
        match = re.search(r"(\d+)", text)
        return int(match.group(1)) * 7 if match else 7
    if "month" in text:
        match = re.search(r"(\d+)", text)
        return int(match.group(1)) * 30 if match else 30

    day_match = re.search(r"(\d+)\s*day", text)
    if day_match:
        return int(day_match.group(1))
    if "day" in text:
        return 1
    return None


class JobQualityFilter:
    """
    Enforces verified-job and minimum company-rating rules before applying.

    Rating check is inclusive at the threshold: ratings at or above
    ``min_company_rating`` pass (e.g. min 3.0 allows 3.0+).
    """

    def __init__(
        self,
        *,
        require_verified: bool = True,
        min_company_rating: float = 3.0,
    ) -> None:
        self.require_verified = require_verified
        self.min_company_rating = min_company_rating

    def evaluate(self, job: Job) -> tuple[bool, str]:
        """Return whether the job passes quality checks and a skip reason."""
        if self.require_verified:
            if job.is_verified is not True:
                if job.is_verified is False:
                    return False, "Job is not verified"
                return False, "Verified status unknown"

        if job.company_rating is None:
            return False, "Company rating unavailable"

        if job.company_rating < self.min_company_rating:
            return (
                False,
                f"Company rating {job.company_rating} is below {self.min_company_rating}",
            )

        return True, ""

    def should_include_at_search(self, job: Job) -> bool:
        """
        Drop jobs at search time only when we already know they fail.

        Jobs missing metadata are kept so the detail page can enrich them.
        """
        if self.require_verified and job.is_verified is False:
            logger.debug(f"Search filter removed unverified job: {job.title} @ {job.company}")
            return False

        if (
            job.company_rating is not None
            and job.company_rating < self.min_company_rating
        ):
            logger.debug(
                f"Search filter removed low-rated job: {job.title} @ {job.company} "
                f"(rating={job.company_rating})"
            )
            return False

        return True
