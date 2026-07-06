"""
Specification Pattern implementation for Job matching and exclusion filters.
Allows composing complex rules via logical operators (AND, OR, NOT).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.naukri_agent.models.entities import Job
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScamScoreResult:
    """Result of a scam score computation."""

    score: int = 0
    raw_score: int = 0
    reasons: list[str] = field(default_factory=list)
    level: str = "safe"


def compute_scam_score(job: Job) -> ScamScoreResult:
    """
    Compute a scam risk score for a job listing using the v4 heuristic algorithm.
    Returns a ScamScoreResult with normalized 0-100 score, raw score, reasons, and category level.
    """
    raw_score = 0
    reasons: list[str] = []

    # Whitelist Shield (-500 pts)
    whitelist_regex = re.compile(
        r"(?i)\b("
        r"tata consultancy services|tcs|wipro|infosys|accenture|cognizant|"
        r"capgemini|ibm|deloitte|kpmg|pwc|ey|ernst & young|amazon|google|"
        r"microsoft|meta|apple|netflix|oracle|cisco|intel|nvidia|muthoot finance"
        r")\b"
    )
    if job.company and whitelist_regex.search(job.company):
        raw_score -= 500
        reasons.append("Whitelist Shield (-500)")

    # Level 1: Financial Scams (Check Description)
    level_1_regex = re.compile(
        r"(?i)\b("
        r"registration fee|security deposit|training charges|laptop charges|"
        r"refundable amount|pay before joining|consultancy charges|"
        r"direct selection without interview|pay amount"
        r")\b"
    )
    if job.description and level_1_regex.search(job.description):
        raw_score += 100
        reasons.append("Financial Scam terms in Description (+100)")

    # Level 1B: Contact Info (Check Title and Company only)
    level_1_contact_regex = re.compile(
        r"(?i)("
        r"(?:(?:\+91|91)[\s-]?)?[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}|"
        r"\b[A-Za-z0-9._%+-]+@(gmail|yahoo|hotmail|outlook|rediffmail)\.com\b"
        r")"
    )
    text_to_check_contact = f"{job.title} {job.company}"
    if level_1_contact_regex.search(text_to_check_contact):
        raw_score += 100
        reasons.append("Contact Info aggressively stuffed in Title/Company (+100)")

    # Level 1C: Agency/Consultancy/Staffing (Check Title and Company)
    level_1_agency_regex = re.compile(
        r"(?i)\b("
        r"consultanc(y|ies)|consultncy|consultant|placement|staffing|manpower|"
        r"recruitment|hr solutions|hr services|outsourcing"
        r")\b"
    )
    text_to_check_agency = f"{job.title} {job.company}"
    if level_1_agency_regex.search(text_to_check_agency):
        raw_score += 100
        reasons.append("Third-party Agency/Consultancy/Placement firm (+100)")

    # Level 2: High Suspicion (Check Title, Company)
    level_2_regex = re.compile(
        r"(?i)\b("
        r"bpo|kpo|voice process|international voice|night shift|outbound|inbound|"
        r"data entry|typist|typing job|telecaller|customer support"
        r")\b"
    )
    text_to_check_l2 = f"{job.title} {job.company}"
    if level_2_regex.search(text_to_check_l2):
        raw_score += 70
        reasons.append("BPO/Staffing terms (+70)")

    # Level 3: Medium Suspicion (Check Title for spam keywords)
    level_3_title_regex = re.compile(
        r"(?i)\b("
        r"walk-?in|walk in|direct joining|urgent(ly)? (hiring|required)|"
        r"mega drive|freshers?|any graduate|no interview|"
        r"bulk hiring|mass recruitment|spot offer|overseas"
        r")\b"
    )
    if job.title and level_3_title_regex.search(job.title):
        raw_score += 40
        reasons.append("Spam/Walk-in terms in Title (+40)")

    # Level 4: Low Suspicion (Check Company name)
    level_4_company_regex = re.compile(
        r"(?i)\b(" r"associates|enterprises|ventures|synergies|solutions pvt ltd" r")\b|\bhr\b$"
    )
    if job.company and level_4_company_regex.search(job.company):
        raw_score += 30
        reasons.append("Suspicious Company Name suffix (+30)")

    # Normalize to 0-100 for display
    display_score = max(0, min(100, raw_score))

    # Determine category
    if raw_score >= 100:
        level = "suspicious"
    elif raw_score >= 30:
        level = "moderate"
    else:
        level = "safe"

    return ScamScoreResult(
        score=display_score,
        raw_score=raw_score,
        reasons=reasons,
        level=level,
    )


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
        self._specs = tuple(specs)

    def is_satisfied_by(self, job: Job) -> bool:
        return all(spec.is_satisfied_by(job) for spec in self._specs)


class OrSpecification(JobSpecification):
    """Logical OR composite specification."""

    def __init__(self, *specs: JobSpecification) -> None:
        self._specs = tuple(specs)

    def is_satisfied_by(self, job: Job) -> bool:
        return any(spec.is_satisfied_by(job) for spec in self._specs)


class NotSpecification(JobSpecification):
    """Logical NOT composite specification."""

    def __init__(self, spec: JobSpecification) -> None:
        self._spec = spec

    def is_satisfied_by(self, job: Job) -> bool:
        return not self._spec.is_satisfied_by(job)


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
    Specification that is satisfied if the job's description contains any configured exclusion keywords.
    Uses pre-compiled O(N) regex matching for speed.
    """

    def __init__(self, keywords: list[str]) -> None:
        self._keywords = keywords
        self._regex: re.Pattern[str] | None = None
        if keywords:
            # Word boundary ensures we don't accidentally match partial words
            pattern = "|".join(rf"\b{re.escape(k)}\b" for k in keywords)
            self._regex = re.compile(pattern, re.IGNORECASE)

    def is_satisfied_by(self, job: Job) -> bool:
        if not self._regex:
            return False
        description = job.description
        if description and self._regex.search(description):
            logger.info("Excluded description keyword match")
            return True
        return False


class ConsultancyScamSpecification(JobSpecification):
    """
    Advanced multi-layered heuristic algorithm (v4) to identify and exclude non-genuine companies,
    consultancies, and scam/spam jobs using a finely tuned mathematical scoring system.
    Tuned to aggressively minimize false positives for genuine jobs.
    """

    SCAM_THRESHOLD = 100

    def is_satisfied_by(self, job: Job) -> bool:
        result = compute_scam_score(job)
        if result.raw_score >= self.SCAM_THRESHOLD:
            reason_str = ", ".join(result.reasons)
            logger.info(
                f"Excluded by Scam Detector v4 (Score: {result.raw_score}): {job.title} @ {job.company}. Reasons: {reason_str}"
            )
            return True
        return False


class AuthenticityExclusionSpecification(JobSpecification):
    """
    Specification that evaluates the authenticity of a job.
    Excludes jobs if the company matches a blocklist, or if it lacks a verified company logo
    while having an unusually high number of openings.
    """

    def __init__(self, blocklist: list[str], max_openings_without_logo: int) -> None:
        self._max_openings = max_openings_without_logo
        self._regex: re.Pattern[str] | None = None
        if blocklist:
            pattern = "|".join(map(re.escape, blocklist))
            self._regex = re.compile(pattern, re.IGNORECASE)

        # Pattern to catch hidden companies (e.g., "MNC", "Confidential", "Leading IT Client")
        self._hidden_company_regex = re.compile(
            r"^(mnc|confidential|startup|leading it company|top it client|client of\b)",
            re.IGNORECASE,
        )

    def is_satisfied_by(self, job: Job) -> bool:
        company = job.company

        # 1. Check against explicitly blocked spam/fake companies
        if company and self._regex and self._regex.search(company):
            logger.info(f"Authenticity Filter: Excluded due to blocked company name: '{company}'")
            return True

        # 2. Check for hidden/generic company names (like the 'MNC' posted by Tele Infotech)
        if company and self._hidden_company_regex.match(company.strip()):
            logger.info(
                f"Authenticity Filter: Excluded due to generic/hidden company name: '{company}'"
            )
            return True

        # 3. Check for missing logo and suspiciously high openings
        if not job.has_company_logo and job.openings >= self._max_openings:
            logger.info(
                f"Authenticity Filter: Excluded '{job.title} @ {company}' due to high openings ({job.openings}) without a verified company logo."
            )
            return True

        return False
