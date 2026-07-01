"""
Specification Pattern implementation for Job matching and exclusion filters.
Allows composing complex rules via logical operators (AND, OR, NOT).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


class JobSpecification(ABC):
    """
    Base Specification class for evaluating criteria on Job entities.
    Supports logical operators: & (AND), | (OR), and ~ (NOT).
    """

    @abstractmethod
    def is_satisfied_by(self, job: Job) -> bool:
        """
        Evaluate the specification against a Job candidate.

        Args:
            job: The Job entity to evaluate.

        Returns:
            True if the job satisfies the specification, False otherwise.
        """
        pass

    def __and__(self, other: JobSpecification) -> JobSpecification:
        return AndSpecification(self, other)

    def __or__(self, other: JobSpecification) -> JobSpecification:
        return OrSpecification(self, other)

    def __invert__(self) -> JobSpecification:
        return NotSpecification(self)


class AndSpecification(JobSpecification):
    """Logical AND composite specification."""

    def __init__(self, *specs: JobSpecification) -> None:
        self._specs = list(specs)

    def is_satisfied_by(self, job: Job) -> bool:
        return all(spec.is_satisfied_by(job) for spec in self._specs)


class OrSpecification(JobSpecification):
    """Logical OR composite specification."""

    def __init__(self, *specs: JobSpecification) -> None:
        self._specs = list(specs)

    def is_satisfied_by(self, job: Job) -> bool:
        return any(spec.is_satisfied_by(job) for spec in self._specs)


class NotSpecification(JobSpecification):
    """Logical NOT composite specification."""

    def __init__(self, spec: JobSpecification) -> None:
        self._spec = spec

    def is_satisfied_by(self, job: Job) -> bool:
        return not self._spec.is_satisfied_by(job)


class BigCompanyAllowlistSpecification(JobSpecification):
    """
    Specification satisfied when the job's company matches the big-company allowlist.
    Empty allowlist matches nothing (all jobs are skipped).
    """

    def __init__(self, companies: list[str]) -> None:
        self._companies = companies
        self._regex: re.Pattern[str] | None = None
        if companies:
            pattern = "|".join(map(re.escape, companies))
            self._regex = re.compile(pattern, re.IGNORECASE)

    def is_satisfied_by(self, job: Job) -> bool:
        if not self._regex:
            return False
        company = job.company
        if company and self._regex.search(company):
            return True
        return False


class CompanyExclusionSpecification(JobSpecification):
    """
    Specification that is satisfied if the job's company is in the configured exclusion list.
    Uses pre-compiled O(N) regex matching for speed.
    """

    def __init__(self, companies: list[str]) -> None:
        self._companies = companies
        self._regex: re.Pattern[str] | None = None
        if companies:
            pattern = "|".join(map(re.escape, companies))
            self._regex = re.compile(pattern, re.IGNORECASE)

    def is_satisfied_by(self, job: Job) -> bool:
        if not self._regex:
            return False
        company = job.company
        if company and self._regex.search(company):
            logger.info(f"Excluded company match: {company}")
            return True
        return False


class TitleExclusionSpecification(JobSpecification):
    """
    Specification that is satisfied if the job's title contains any of the configured exclusion keywords.
    Uses pre-compiled O(N) regex matching for speed.
    """

    def __init__(self, keywords: list[str]) -> None:
        self._keywords = keywords
        self._regex: re.Pattern[str] | None = None
        if keywords:
            pattern = "|".join(map(re.escape, keywords))
            self._regex = re.compile(pattern, re.IGNORECASE)

    def is_satisfied_by(self, job: Job) -> bool:
        if not self._regex:
            return False
        title = job.title
        if title and self._regex.search(title):
            logger.info(f"Excluded title match: {title}")
            return True
        return False


class DescriptionExclusionSpecification(JobSpecification):
    """
    Specification that is satisfied if the job's description contains any of the configured exclusion keywords.
    Uses pre-compiled O(N) regex matching for speed.
    """

    def __init__(self, keywords: list[str]) -> None:
        self._keywords = keywords
        self._regex: re.Pattern[str] | None = None
        if keywords:
            pattern = "|".join(map(re.escape, keywords))
            self._regex = re.compile(pattern, re.IGNORECASE)

    def is_satisfied_by(self, job: Job) -> bool:
        if not self._regex:
            return False
        description = job.description
        if description and self._regex.search(description):
            logger.info("Excluded description keyword match")
            return True
        return False
