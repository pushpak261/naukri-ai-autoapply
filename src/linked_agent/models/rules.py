"""
LinkedIn-specific scam detection and job exclusion rules.

Uses a weighted scoring approach similar to the Naukri agent, adapted
for LinkedIn-specific signals (recruitment agencies, BPO spam, etc.).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.linked_agent.models.entities import Job
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class JobSpecification(ABC):
    """Base class for composable job specifications."""

    @abstractmethod
    def is_satisfied_by(self, job: Job) -> bool:
        ...

    def __and__(self, other: "JobSpecification") -> "ComposedSpecification":
        return ComposedSpecification(self, other, operator="and")

    def __or__(self, other: "JobSpecification") -> "ComposedSpecification":
        return ComposedSpecification(self, other, operator="or")

    def __invert__(self) -> "NotSpecification":
        return NotSpecification(self)


class ComposedSpecification(JobSpecification):
    """Composes two specifications with AND/OR logic."""

    def __init__(self, left: JobSpecification, right: JobSpecification, operator: str) -> None:
        self._left = left
        self._right = right
        self._operator = operator

    def is_satisfied_by(self, job: Job) -> bool:
        if self._operator == "and":
            return self._left.is_satisfied_by(job) and self._right.is_satisfied_by(job)
        return self._left.is_satisfied_by(job) or self._right.is_satisfied_by(job)


class NotSpecification(JobSpecification):
    """Negates a specification."""

    def __init__(self, spec: JobSpecification) -> None:
        self._spec = spec

    def is_satisfied_by(self, job: Job) -> bool:
        return not self._spec.is_satisfied_by(job)


class CompanyExclusionSpecification(JobSpecification):
    """Excludes jobs from specific companies."""

    def __init__(self, excluded_companies: list[str]) -> None:
        self._excluded = {c.lower().strip() for c in excluded_companies if c.strip()}

    def is_satisfied_by(self, job: Job) -> bool:
        return job.company.lower().strip() in self._excluded


class TitleExclusionSpecification(JobSpecification):
    """Excludes jobs with specific title keywords."""

    def __init__(self, excluded_keywords: list[str]) -> None:
        self._keywords = [k.lower().strip() for k in excluded_keywords if k.strip()]

    def is_satisfied_by(self, job: Job) -> bool:
        title_lower = job.title.lower()
        return any(kw in title_lower for kw in self._keywords)


class DescriptionExclusionSpecification(JobSpecification):
    """Excludes jobs with specific description keywords."""

    def __init__(self, excluded_keywords: list[str]) -> None:
        self._keywords = [k.lower().strip() for k in excluded_keywords if k.strip()]

    def is_satisfied_by(self, job: Job) -> bool:
        desc_lower = job.description.lower()
        return any(kw in desc_lower for kw in self._keywords)


class LinkedInScamSpecification(JobSpecification):
    """
    Detects suspicious jobs on LinkedIn using weighted scoring.

    LinkedIn-specific signals:
    - Recruitment agency patterns
    - BPO/KPO spam
    - "Urgent hiring" + suspicious company
    - Work-from-home + immediate join
    - Freshers + bulk hiring patterns
    """

    # Positive = scam signal, Negative = genuine signal
    SCAM_SIGNALS: list[tuple[str, float]] = [
        # Company name signals
        (r"\b(recruitment|recruiting|staffing|manpower)\b", 30),
        (r"\b(bpo|kpo|back office|voice process)\b", 25),
        (r"\b(international process|international voice)\b", 35),
        (r"\b(non voice|non-voice)\b", 20),
        (r"\b(data entry|form filling)\b", 25),

        # Title signals
        (r"\b(fresher[s]?\s+required|bulk\s+hiring)\b", 30),
        (r"\b(urgent\s+hiring|immediate\s+joining)\b", 15),
        (r"\b(work\s+from\s+home.*earn|earn\s+\d+k?\s+daily)\b", 40),
        (r"\b(small\s+investment|investment\s+required)\b", 50),
        (r"\b(unlimited\s+income|no\s+salary\s+ceiling)\b", 45),

        # Description signals
        (r"\b(whatsapp|telegram|call\s+for\s+details)\b", 35),
        (r"\b(fee\s+required|registration\s+fee|security\s+deposit)\b", 50),
        (r"\b(no\s+experience\s+needed|zero\s+experience\s+required)\b", 10),
        (r"\b(guaranteed\s+job|100%\s+job\s+guarantee)\b", 45),
    ]

    GENUINE_SIGNALS: list[tuple[str, float]] = [
        (r"\b(tech|software|engineering|development)\b", -10),
        (r"\b(mnc|multinational)\b", -15),
        (r"\b(glassdoor|ambitionbox|linked(?:in)?\s+top)\b", -10),
        (r"\b(\d{4,}\+?\s+employees)\b", -10),
    ]

    def is_satisfied_by(self, job: Job) -> bool:
        score = self.compute_scam_score(job)
        return score >= 80

    @classmethod
    def compute_scam_score(cls, job: Job) -> float:
        """Compute a weighted scam score (0-100)."""
        text = f"{job.title} {job.company} {job.description}".lower()

        score = 0.0
        for pattern, weight in cls.SCAM_SIGNALS:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight

        for pattern, weight in cls.GENUINE_SIGNALS:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight  # weight is negative

        return max(0, min(100, score))


# ---------------------------------------------------------------------------
# ScamScoreResult for ConsultancyScamSpecification
# ---------------------------------------------------------------------------
@dataclass
class ScamScoreResult:
    """Result of a scam score computation."""

    score: int = 0
    raw_score: int = 0
    reasons: list[str] = field(default_factory=list)
    level: str = "safe"


# ---------------------------------------------------------------------------
# Pre-compiled regex patterns for scam detection (adapted from Naukri v6)
# ---------------------------------------------------------------------------

_WHITELIST_RE = re.compile(
    r"(?i)\b("
    r"tata consultancy services|tcs|wipro|infosys|accenture|cognizant|"
    r"capgemini|ibm|deloitte|kpmg|pwc|ey|ernst & young|amazon|google|"
    r"microsoft|meta|apple|netflix|oracle|cisco|intel|nvidia|"
    r"l&t|ltimindtree|tech mahindra|hcl|hexaware|mindtree|zoho|"
    r"zomato|swiggy|flipkart|paytm|razorpay|samsung|adobe|salesforce|"
    r"uber|airbnb|spotify|twitter|x|linkedin|shopify|atlassian|"
    r"vmware|dell|hp|siemens|bosch|philips|nokia|sap"
    r")\b"
)

_TECH_SKILLS_RE = re.compile(
    r"(?i)\b("
    r"python|java|javascript|typescript|react|angular|vue|node\.?js|"
    r"django|flask|spring|springboot|fastapi|express|next\.?js|"
    r"sql|mysql|postgresql|mongodb|redis|kafka|rabbitmq|"
    r"aws|azure|gcp|docker|kubernetes|terraform|jenkins|"
    r"git|rest\s*api|graphql|microservices|ci/cd"
    r")\b"
)

_FINANCIAL_SCAM_RE = re.compile(
    r"(?i)\b("
    r"registration fee|security deposit|training charges|laptop charges|"
    r"refundable amount|pay before joining|consultancy charges|"
    r"direct selection without interview|pay amount"
    r")\b"
)

_PHONE_RE = re.compile(
    r"(?i)(?:(?:\+91|91)[\s-]?)?[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}"
)

_EMAIL_RE = re.compile(
    r"(?i)\b[A-Za-z0-9._%+-]+@(gmail|yahoo|hotmail|outlook|rediffmail)\.com\b"
)

_AGENCY_RE = re.compile(
    r"(?i)\b("
    r"consultanc(y|ies)|consultncy|consulting|placement|staffing|manpower|"
    r"recruitment|hr\b|hr solutions|hr services|hr consultancy|"
    r"outsourcing|talent acquisition|talent solution|"
    r"manpower services|placement agency|"
    r"career services|career solution|career guidance|career consultant|"
    r"talent services|hiring solution|job placement|placement service|"
    r"staffing solution|hiring agency|recruiter services|staffing agency|"
    r"job consultanc(y|ies)|talent partner|workforce solution"
    r")\b"
)

_EDUCATION_TRAINING_RE = re.compile(
    r"(?i)\b("
    r"education foundation|educational trust|training institute|"
    r"training company|coaching centre|learning solution|"
    r"academy of|skill development|career solution"
    r")\b"
)

_GENERIC_SERVICES_RE = re.compile(
    r"(?i)\b("
    r"management services|management consultancy|management solutions|"
    r"global services|enterprise services|global solutions|"
    r"business services|corporate services|business solutions|"
    r"it services|it solutions|technology services|tech services"
    r")\b"
)

_BPO_RE = re.compile(
    r"(?i)\b("
    r"bpo|kpo|voice process|international voice|night shift|outbound|inbound|"
    r"data entry|typist|typing job|telecaller|customer support"
    r")\b"
)

_WALKIN_RE = re.compile(
    r"(?i)\b("
    r"walk-?in|walk in|direct joining|urgent(ly)? (hiring|required)|"
    r"mega drive|no interview|bulk hiring|mass recruitment|spot offer"
    r")\b"
)

_HIDDEN_COMPANY_RE = re.compile(
    r"^(mnc|confidential|startup|leading it company|top it client|top mnc|"
    r"leading client|confidential client|client company|client of\b|"
    r"a leading company|a top company|reputed mnc|our client|undisclosed)",
    re.IGNORECASE,
)

_COMPANY_SUFFIX_RE = re.compile(
    r"(?i)\b(associates|enterprises|ventures|synergies|manpower|recruiters)\b"
)

_OVERSEAS_RECRUITER_RE = re.compile(
    r"(?i)\b("
    r"germany\s*(jobs?|guide|work|opportunity)|abroad\s*(jobs?|work|opportunity)|"
    r"overseas\s*(jobs?|work|placement)|work\s*in\s*(germany|canada|australia|uk|usa)|"
    r"global\s*(career|placement|jobs?|guide)|international\s*(placement|staffing|recruitment)|"
    r"immigration\s*(consultant|service)|visa\s*(consultant|service|assistance)|"
    r"foreign\s*(job|placement|opportunity)"
    r")\b"
)

_MULTIPLE_PHONES_RE = re.compile(
    r"(?:(?:\+91|91)[\s\-]?)?[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{4}"
)

_SOLUTIONS_COMPANY_RE = re.compile(
    r"(?i)^[\w\s]{2,30}\s+(management|career|hr|business|global|job|talent|work)\s+solutions?\s*$"
)

_WHATSAPP_RE = re.compile(
    r"(?i)whatsapp[\s\-]*?(?:\+91|91|0)?[6-9]\d{7,9}"
)

_RESUME_REQUEST_RE = re.compile(
    r"(?i)(send|share|forward|email|whatsapp)\s*(your|the|ur)?\s*(resume|cv)"
)

_CONTACT_HR_RE = re.compile(
    r"(?i)(contact\s*(hr|us|recruiter|team|immediately))|(call\s*(hr|us|recruiter))|"
    r"(whatsapp\s*(your\s*)?resume)"
)

_FRESHERS_AD_RE = re.compile(
    r"(?i)(freshers?\s*(welcome|can apply|eligible|required|needed|preferred|appreciated)|"
    r"\b(bca|bsc|b\.?tech|b\.?e|be|mca|m\.?tech|m\.?sc|"
    r"bachelor|master)\s*(freshers?|graduates?|candidates?|students?)|"
    r"any\s*graduate|freshers?\s*only|"
    r"hiring\s*(for|of)?\s*(bca|bsc|btech|mca|graduate))"
)

_GENERIC_DESC_RE = re.compile(
    r"(?i)\b("
    r"good communication skills|excellent communication skills|"
    r"basic programming knowledge|basic computer knowledge|"
    r"good verbal communication|good written communication|"
    r"willing to learn|quick learner|team player|"
    r"positive attitude|self.?motivated|hard working|"
    r"good interpersonal skills|presentable personality"
    r")\b"
)

_MULTI_CITY_RE = re.compile(
    r"(?i)(?:location|openings?|hiring|posting|position)"
    r"(?:\s*[:]\s*|\s+(?:in|for|at)\s+|\s+)?"
    r"(?:bangalore|bengaluru|pune|mumbai|hyderabad|chennai|madras|"
    r"delhi|new delhi|noida|gurgaon|gurugram|"
    r"kolkata|calcutta|ahmedabad|indore|"
    r"jaipur|lucknow|chandigarh|kochi|cochin|"
    r"trivandrum|thiruvananthapuram|vizag|visakhapatnam)\s*"
    r"(?:[,\/\-&]+\s*|\s+and\s+)"
    r"(?:bangalore|bengaluru|pune|mumbai|hyderabad|chennai|"
    r"delhi|noida|gurgaon|kolkata|ahmedabad|indore)"
)

_IMMEDIATE_JOIN_RE = re.compile(
    r"(?i)(immediate\s*(joining|joiner|requirement|need|position|hire)|"
    r"urgent\s*(requirement|hiring|need|position)|"
    r"join\s*immediately|"
    r"candidates?\s*who\s*can\s*join\s*immediately)"
)

_DATE_IN_COMPANY_RE = re.compile(
    r"(?i)\b(19|20)\d{2}\b"
)


def _count_tech_categories(description: str) -> int:
    """Count distinct technology categories in a description."""
    categories = 0
    if re.search(r"(?i)\b(python|java|javascript|typescript|go|rust|ruby|php|c#|c\+\+|scala|kotlin|swift)\b", description):
        categories += 1
    if re.search(r"(?i)\b(react|angular|vue|svelte|next\.?js|nuxt|sass|html|css|jquery|bootstrap|tailwind)\b", description):
        categories += 1
    if re.search(r"(?i)\b(django|flask|spring|springboot|fastapi|express|laravel|rails|asp\.net|node\.?js)\b", description):
        categories += 1
    if re.search(r"(?i)\b(sql|mysql|postgresql|mongodb|redis|oracle|sqlite|mariadb|dynamodb|elasticsearch|cassandra)\b", description):
        categories += 1
    if re.search(r"(?i)\b(aws|azure|gcp|docker|kubernetes|terraform|jenkins|ansible|cloud|devops|ci/cd)\b", description):
        categories += 1
    return categories


def compute_scam_score(job: Job) -> ScamScoreResult:
    """
    Compute a scam risk score for a job listing using the v6 heuristic algorithm.
    Adapted from Naukri agent for LinkedIn job listings.
    """
    raw_score = 0
    reasons: list[str] = []
    combined_text = f"{job.title} {job.company}"
    desc_text = job.description or ""

    # Genuine signals
    if job.company and _WHITELIST_RE.search(job.company):
        raw_score -= 500
        reasons.append("Known reputed company (-500)")

    if job.has_company_logo:
        raw_score -= 30
        reasons.append("Verified company logo (-30)")

    if desc_text:
        tech_match = _TECH_SKILLS_RE.search(desc_text)
        tech_categories = _count_tech_categories(desc_text)
        if tech_match and tech_categories >= 2 and len(desc_text) > 400:
            raw_score -= 50
            reasons.append(f"Detailed technical description with {tech_categories} tech categories (-50)")
        elif tech_match:
            raw_score -= 20
            reasons.append("Technical skills in description (-20)")

    # Scam signals
    if desc_text and _FINANCIAL_SCAM_RE.search(desc_text):
        raw_score += 200
        reasons.append("Financial scam terms in description (+200)")

    if desc_text and _WHATSAPP_RE.search(desc_text):
        raw_score += 120
        reasons.append("WhatsApp number in description (+120)")

    if desc_text and _RESUME_REQUEST_RE.search(desc_text):
        raw_score += 80
        reasons.append("Resume request in description (+80)")

    if desc_text and _CONTACT_HR_RE.search(desc_text):
        raw_score += 60
        reasons.append("Contact HR/recruiter in description (+60)")

    if desc_text and _FRESHERS_AD_RE.search(desc_text):
        raw_score += 70
        reasons.append("Freshers advertisement wording (+70)")

    if desc_text and _GENERIC_DESC_RE.search(desc_text):
        raw_score += 50
        reasons.append("Generic description (soft skills only) (+50)")

    if desc_text and _MULTI_CITY_RE.search(desc_text):
        raw_score += 60
        reasons.append("Multiple city hiring in description (+60)")

    if desc_text and _IMMEDIATE_JOIN_RE.search(desc_text):
        raw_score += 50
        reasons.append("Immediate joining/urgent hiring language (+50)")

    if desc_text and len(desc_text) < 150 and not _TECH_SKILLS_RE.search(desc_text):
        raw_score += 60
        reasons.append("Very short description without technical details (+60)")

    if _PHONE_RE.search(combined_text):
        raw_score += 100
        reasons.append("Phone number in title/company (+100)")

    if _EMAIL_RE.search(combined_text):
        raw_score += 100
        reasons.append("Personal email in title/company (+100)")

    in_company = job.company and _AGENCY_RE.search(job.company)
    in_title = job.title and _AGENCY_RE.search(job.title)
    if in_company:
        raw_score += 200
        reasons.append("Agency/consultancy keywords in company (+200)")
    elif in_title:
        raw_score += 100
        reasons.append("Agency/consultancy keywords in title (+100)")

    if job.company and _EDUCATION_TRAINING_RE.search(job.company):
        raw_score += 120
        reasons.append("Education/training company name (+120)")

    if job.company and _GENERIC_SERVICES_RE.search(job.company):
        raw_score += 120
        reasons.append("Generic services company name (+120)")

    if _BPO_RE.search(combined_text):
        raw_score += 100
        reasons.append("BPO/staffing keywords (+100)")

    if job.title and _WALKIN_RE.search(job.title):
        raw_score += 80
        reasons.append("Walk-in/suspicious hiring keywords (+80)")

    if job.company and _HIDDEN_COMPANY_RE.match(job.company.strip()):
        raw_score += 100
        reasons.append("Hidden/generic company name (+100)")

    if job.company and _COMPANY_SUFFIX_RE.search(job.company):
        raw_score += 40
        reasons.append("Suspicious company suffix (+40)")

    if job.company and _DATE_IN_COMPANY_RE.search(job.company):
        raw_score += 50
        reasons.append("Year number in company name (+50)")

    if not job.has_company_logo and job.openings >= 30:
        raw_score += 60
        reasons.append("No logo with high openings (+60)")

    if desc_text:
        phone_matches = _MULTIPLE_PHONES_RE.findall(desc_text)
        if len(phone_matches) >= 3:
            raw_score += 120
            reasons.append(f"Multiple phone numbers in description ({len(phone_matches)} found) (+120)")
        elif len(phone_matches) >= 1:
            raw_score += 40
            reasons.append(f"Phone number(s) in description ({len(phone_matches)} found) (+40)")

    overseas_in_company = job.company and _OVERSEAS_RECRUITER_RE.search(job.company)
    overseas_in_title = job.title and _OVERSEAS_RECRUITER_RE.search(job.title)
    overseas_in_desc = desc_text and _OVERSEAS_RECRUITER_RE.search(desc_text)
    if overseas_in_company or overseas_in_title:
        raw_score += 200
        reasons.append("Overseas/abroad job recruiter in company/title (+200)")
    elif overseas_in_desc:
        raw_score += 80
        reasons.append("Overseas/abroad job placement in description (+80)")

    if job.company and _SOLUTIONS_COMPANY_RE.match(job.company.strip()):
        raw_score += 80
        reasons.append("Company name matches agency solutions pattern (+80)")

    display_score = max(0, min(100, raw_score))
    if raw_score >= 100:
        level = "suspicious"
    elif raw_score >= 30:
        level = "moderate"
    else:
        level = "safe"

    return ScamScoreResult(score=display_score, raw_score=raw_score, reasons=reasons, level=level)


class ConsultancyScamSpecification(JobSpecification):
    """
    Advanced multi-layered heuristic algorithm to identify and exclude non-genuine companies,
    consultancies, placement agencies, staffing firms, education/training institutes,
    and scam/spam jobs using a finely tuned weighted scoring system.
    Adapted from Naukri agent for LinkedIn.
    """

    SCAM_THRESHOLD = 80

    def is_satisfied_by(self, job: Job) -> bool:
        result = compute_scam_score(job)
        if result.raw_score >= self.SCAM_THRESHOLD:
            reason_str = ", ".join(result.reasons)
            logger.info(
                f"Excluded by Scam Detector (Score: {result.raw_score}): {job.title} @ {job.company}. Reasons: {reason_str}"
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

        self._hidden_company_regex = re.compile(
            r"^(mnc|confidential|startup|leading it company|top it client|client of\b)",
            re.IGNORECASE,
        )

    def is_satisfied_by(self, job: Job) -> bool:
        company = job.company

        if company and self._regex and self._regex.search(company):
            logger.info(f"Authenticity Filter: Excluded due to blocked company name: '{company}'")
            return True

        if company and self._hidden_company_regex.match(company.strip()):
            logger.info(f"Authenticity Filter: Excluded due to generic/hidden company name: '{company}'")
            return True

        if not job.has_company_logo and job.openings >= self._max_openings:
            logger.info(
                f"Authenticity Filter: Excluded '{job.title} @ {company}' due to high openings ({job.openings}) without a verified company logo."
            )
            return True

        return False
