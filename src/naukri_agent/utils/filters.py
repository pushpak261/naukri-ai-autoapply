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
        self, max_experience: int, max_freshness_days: int, sort_by: str = "relevance"
    ) -> None:
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
        """Check if the job's experience requirement is within limits.

        Naukri experience strings look like "0-2 Yrs", "3-5 Yrs", "5 Yrs".
        We parse the *minimum* required experience from the range and check
        that it doesn't exceed our configured maximum.
        """
        exp_text = exp_text.lower()

        # If the text contains a month abbreviation, it's likely a walk-in date wrongly parsed as experience
        months = [
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
        ]
        if any(month in exp_text for month in months):
            return True

        # Try to match range format first: "X-Y" or "X to Y"
        range_match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", exp_text)
        if range_match:
            min_req = int(range_match.group(1))
            max_req = int(range_match.group(2))
            if min_req > self.max_experience:
                return False
            if max_req > self.max_experience + 1 and max_req >= 4:
                return False
            return True
        # Single number format: "5 Yrs"
        single_match = re.search(r"(\d+)", exp_text)
        if single_match:
            min_req = int(single_match.group(1))
            if min_req > self.max_experience:
                return False
        return True

    def _passes_freshness_filter(self, date_text: str) -> bool:
        """Check if the job posting age is within limits."""
        if self.max_freshness_days <= 0:
            return True

        days = self._parse_date_to_days(date_text)
        return days <= self.max_freshness_days

    @staticmethod
    def _parse_date_to_days(date_text: str) -> int:
        """Convert a job posting date string to an approximate number of days for sorting."""
        date_text = date_text.lower()
        if (
            "just now" in date_text
            or "today" in date_text
            or "hour" in date_text
            or "minute" in date_text
            or "second" in date_text
        ):
            return 0
        if "yesterday" in date_text:
            return 1
        if "month" in date_text:
            match = re.search(r"(\d+)", date_text)
            return int(match.group(1)) * 30 if match else 30
        if "week" in date_text:
            match = re.search(r"(\d+)", date_text)
            return int(match.group(1)) * 7 if match else 7

        # Handle "30+ days ago"
        if "30+" in date_text:
            return 31

        # Handle "X days ago"
        day_match = re.search(r"(\d+)\s*day", date_text)
        if day_match:
            return int(day_match.group(1))

        # Handle "a day ago" or "day ago"
        if "day" in date_text:
            return 1

        return 999  # Default to very old if unknown
