"""
Core scam detection engine for fake/scam job identification.

Provides:
  - compute_scam_score() — multi-phase heuristic algorithm with 26+ signals
  - ScamScoreResult — structured scoring result with reasons
  - Specification classes for composable exclusion rules
  - Pre-compiled regex patterns for all detection signals

=== ALGORITHM: 5-Phase Weighted Scoring ===

Phase 0 — Input Validation & Text Preparation
    - Handle None/empty fields
    - Normalize combined text for title+company checks
    - Extract description text for description-level checks

Phase 1 — Genuine Signals (negative points, reduce scam score)
    G1: Whitelist company (-500) — known reputed firms like TCS, Google, etc.
    G2: Company logo present (-30) — indicates established business
    G3: Technical skills in description (-20 to -50) — real tech job
    G4: Salary mentioned in description (-15) — legitimate listing practice

Phase 2 — Critical Scam Signals (highest weight, individually critical)
    S1:  Financial scam terms          (+200) — registration fee, deposit, etc.
    S12a: Agency keywords in company   (+200) — placement, staffing, consultancy
    S22a: Overseas recruiter in co/title(+200) — immigration, visa, abroad

Phase 3 — High-Risk Scam Signals (strong indicators)
    S2:   WhatsApp number              (+120)
    S13:  Education/training company   (+120)
    S14:  Generic services company     (+120)
    S21a: 3+ phone numbers in desc    (+120)
    S10:  Phone in title/company       (+100)
    S11:  Personal email in co/title   (+100)
    S15:  BPO/staffing keywords        (+100)
    S17:  Hidden company name          (+100)
    S12b: Agency keywords in title     (+100)
    S25:  Social media handle in desc  (+80)  — Telegram/Instagram recruitment

Phase 4 — Medium-Risk Scam Signals (stack together to exclude)
    S16:  Walk-in hiring               (+80)
    S23:  Agency solutions pattern     (+80)
    S22b: Overseas in description      (+80)
    S3:   Resume request               (+80)
    S5:   Freshers advertisement       (+70)
    S7:   Multi-city hiring            (+60)
    S9:   Short desc, no tech          (+60)
    S20:  No logo + high openings      (+60)
    S4:   Contact HR/recruiter         (+60)
    S24:  WFH with unrealistic earning (+60)
    S6:   Generic description          (+50)
    S8:   Immediate joining            (+50)
    S19:  Year in company name         (+50)
    S21b: 1-2 phone numbers in desc   (+40)
    S18:  Suspicious company suffix    (+40)
    S26:  URL shortener in desc        (+40)

Phase 5 — Scoring & Classification
    raw_score = sum of all genuine + scam signal weights
    display_score = clamp(raw_score, 0, 100)
    Classification:
      suspicious (excluded):  raw_score >= 80
      moderate:               raw_score >= 30
      safe:                   raw_score < 30

Design principles:
    1. Agency keywords in company (+200) outweigh ALL genuine signals
       EXCEPT the whitelist (-500). This ensures placement/staffing firms
       are always excluded unless they're a known reputed company.
    2. No single non-critical signal reaches threshold alone — at least
       2 medium-risk signals must stack.
    3. Genuine signals provide a safety net for legitimate listings that
       happen to contain some scam-like patterns (e.g., a startup with
       a contact number in the description).
    4. Multi-signal stacking prevents any single rule from causing a
       false positive.
    5. All signals are purely regex/heuristic — no AI dependency.
"""

from __future__ import annotations

import re
from typing import Any
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.naukri_agent.models.entities import Job
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)

# ======================================================================
# Constants
# ======================================================================

# Tech name normalization for regex matching (c# → csharp, c++ → cpp, f# → fsharp)
_TECH_NORMALIZE: dict[str, str] = {
    "c#": "csharp",
    "c++": "cpp",
    "f#": "fsharp",
}

SCAM_THRESHOLD = 80
"""Jobs with raw_score >= SCAM_THRESHOLD are excluded as scam/consultancy."""

EARLY_SCAM_THRESHOLD = 200
"""
Higher threshold for early (pre-description) scam pass.
Only catches undeniable scams when we have only title+company:
  - Agency keywords in company name (+200)
  - Overseas recruiter in company/title (+200)
  - Financial scam terms in description (+200)
Everything below 200 passes through to be re-evaluated with full description data.
"""

MODERATE_THRESHOLD = 30
"""Jobs with raw_score >= MODERATE_THRESHOLD but < SCAM_THRESHOLD are moderate risk."""


# ======================================================================
# Data Structures
# ======================================================================

@dataclass
class ScamScoreResult:
    """
    Result of a scam score computation.

    Attributes:
        score:       Display score clamped to [0, 100].
        raw_score:   Unclamped raw sum of all signal weights.
        reasons:     Human-readable list of triggered signals.
        level:       Classification: "safe", "moderate", or "suspicious".
    """
    score: int = 0
    raw_score: int = 0
    reasons: list[str] = field(default_factory=list)
    level: str = "safe"


# ======================================================================
# PHASE 0: Pre-compiled Regex Patterns
# ======================================================================

# ------------------------------------------------------------------
# Phase 1 — Genuine Signal Patterns
# ------------------------------------------------------------------

# G1: Known reputed companies (overrides all other signals)
_WHITELIST_RE = re.compile(
    r"(?i)\b("
    r"tata consultancy services|tcs|wipro|infosys|accenture|cognizant|"
    r"capgemini|ibm|deloitte|kpmg|pwc|ey|ernst & young|amazon|google|"
    r"microsoft|meta|apple|netflix|oracle|cisco|intel|nvidia|muthoot finance|"
    r"l&t|ltimindtree|tech mahindra|hcl|hexaware|mindtree|zoho|"
    r"zomato|swiggy|flipkart|paytm|razorpay|"
    r"saviynt|mastercard|qualcomm|goldman sachs|voxelgrids|davies|"
    r"jpmorgan|jpmc|goldman|sap|salesforce|servicenow|workday|vmware|"
    r"adobe|paypal|cisco|intuit|uber|booking|expedia|walmart|target|"
    r"sony|samsung|motorola|vmware|genpact|exl|ntt data|nttdata"
    r")\b"
)

# G3: Technical skills in description (indicates a real tech job)
_TECH_SKILLS_RE = re.compile(
    r"(?i)\b("
    r"python|java|javascript|typescript|go|rust|ruby|php|csharp|cpp|fsharp|scala|kotlin|swift|"
    r"react|angular|vue|svelte|next\.?js|nuxt|sass|html|css|jquery|bootstrap|tailwind|"
    r"django|flask|spring|springboot|fastapi|express|laravel|rails|asp\.net|node\.?js|"
    r"sql|mysql|postgresql|mongodb|redis|kafka|rabbitmq|oracle|sqlite|mariadb|"
    r"aws|azure|gcp|docker|kubernetes|terraform|jenkins|ansible|cloud|devops|ci/cd|"
    r"git|rest\s*api|graphql|microservices"
    r")\b"
)

# G4: Salary indicator in description
_SALARY_RE = re.compile(
    r"(?i)(?:salary|ctc|pay|package|stipend|compensation)\s*(?::|is|:–)?\s*(?:\d[\d,.-]*(?:\s*(?:lpa|lakh|k|per annum|pa|monthly|pm))?)"
)

# ------------------------------------------------------------------
# Phase 2 — Critical Scam Signal Patterns
# ------------------------------------------------------------------

# S1: Financial fraud indicators
_FINANCIAL_SCAM_RE = re.compile(
    r"(?i)\b("
    r"registration fee|security deposit|training charges|laptop charges|"
    r"refundable amount|pay before joining|consultancy charges|"
    r"direct selection without interview|pay amount"
    r")\b"
)

# S12: Agency / placement / staffing keywords in title or company
_AGENCY_RE = re.compile(
    r"(?i)\b("
    r"consultanc(y|ies)|consultant|consultants|consultncy|consulting|"
    r"placement|staffing|manpower|recruitment|recruiter|recruiters|"
    r"headhunter|headhunters|advisors|advisory|hr\b|hr solutions|hr services|"
    r"hr consultancy|hr consultant|hr recruiters|outsourcing|talent acquisition|"
    r"talent solution|talent solutions|talent partner|manpower services|"
    r"placement agency|placement consultant|recruitment consultant|"
    r"career services|career solution|career guidance|career consultant|"
    r"talent services|hiring solution|hiring partner|hiring agency|"
    r"job placement|placement service|staffing solution|staffing agency|"
    r"recruiter services|job consultanc(y|ies)|job consultant|"
    r"workforce solution|workforce solutions|partner consultant"
    r")\b"
)

# S22: Overseas / abroad job recruiters
_OVERSEAS_RECRUITER_RE = re.compile(
    r"(?i)\b("
    r"germany\s*(jobs?|guide|work|opportunity)|abroad\s*(jobs?|work|opportunity)|"
    r"overseas\s*(jobs?|work|placement)|work\s*in\s*(germany|canada|australia|uk|usa)|"
    r"global\s*(career|placement|jobs?|guide)|international\s*(placement|staffing|recruitment)|"
    r"immigration\s*(consultant|service|help|agency|firm|center|centre|desk|expert)|"
    r"visa\s*(consultant|service|assistance|help|agency|firm|center|centre|expert)|"
    r"foreign\s*(job|placement|opportunity)"
    r")\b"
)

# ------------------------------------------------------------------
# Phase 3 — High-Risk Scam Signal Patterns
# ------------------------------------------------------------------

# S2: WhatsApp number
_WHATSAPP_RE = re.compile(
    r"(?i)whatsapp[\s\-]*?(?:\+91|91|0)?[\s\-]*?[6-9]\d{7,9}"
)

# S10: Phone number in title or company
_PHONE_RE = re.compile(
    r"(?i)(?:(?:\+91|91)[\s-]?)?[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}"
)

# S11: Personal email domain in title or company
_EMAIL_RE = re.compile(
    r"(?i)\b[A-Za-z0-9._%+-]+@(gmail|yahoo|hotmail|outlook|rediffmail|protonmail|icloud|aol|yandex|mail\.ru|zoho)\.com\b"
)

# S13: Education/training institutes masquerading as IT companies
_EDUCATION_TRAINING_RE = re.compile(
    r"(?i)\b("
    r"education foundation|educational trust|training institute|"
    r"training company|coaching centre|learning solution|"
    r"academy of|skill development|career solution"
    r")\b"
)

# S14: Generic services/solutions companies
_GENERIC_SERVICES_RE = re.compile(
    r"(?i)\b("
    r"management services|management consultancy|management solutions|"
    r"global services|enterprise services|global solutions|"
    r"business services|corporate services|business solutions|"
    r"it services|it solutions|technology services|tech services"
    r")\b"
)

# S15: BPO / call-centre / data-entry keywords
_BPO_RE = re.compile(
    r"(?i)\b("
    r"bpo|kpo|voice process|international voice|night shift|outbound|inbound|"
    r"data entry|typist|typing job|telecaller|customer support"
    r")\b"
)

# S17: Hidden / generic company name
_HIDDEN_COMPANY_RE = re.compile(
    r"^(mnc\b|confidential\b|startup\b|leading it company|top it client|top mnc\b|"
    r"leading client|confidential client|client company|client of\b|"
    r"a leading company|a top company|reputed mnc|our client|undisclosed)",
    re.IGNORECASE,
)

# S25: Social media handle in description (Telegram, Instagram)
# Uses @\w+(?=[^\w.]|$) to match bare social handles (@company) while
# rejecting email addresses ("hr@gmail.com" → @gmail followed by . → fail).
# Email-based signals are caught separately by _EMAIL_RE (+100).
_SOCIAL_MEDIA_RE = re.compile(
    r"(?i)(?:t(?:elegram)?\.?me/|@\w+(?=[^\w.]|$)|instagram\.com/|wa\.me/|"
    r"join\s*(?:our|the)\s*(?:telegram|whatsapp)\s*(?:group|channel))"
)

# ------------------------------------------------------------------
# Phase 4 — Medium-Risk Scam Signal Patterns
# ------------------------------------------------------------------

# S3: Resume request
_RESUME_REQUEST_RE = re.compile(
    r"(?i)(send|share|forward|email|whatsapp)\s*(your|the|ur)?\s*(resume|cv)"
)

# S4: Contact HR / recruiter directly
_CONTACT_HR_RE = re.compile(
    r"(?i)(contact\s*(hr|us|recruiter|team|immediately))|(call\s*(hr|us|recruiter))|"
    r"(whatsapp\s*(your\s*)?resume)"
)

# S5: Freshers advertisement patterns
_FRESHERS_AD_RE = re.compile(
    r"(?i)(freshers?\s*(welcome|can apply|eligible|required|needed|preferred|appreciated)|"
    r"\b(bca|bsc|b\.?tech|b\.?e|mca|m\.?tech|m\.?sc|"
    r"bachelor|master)\s*(freshers?|graduates?|candidates?|students?)|"
    r"any\s*graduate|freshers?\s*only|"
    r"hiring\s*(for|of)?\s*(bca|bsc|btech|mca|graduate))"
)

# S6: Generic description with no technical specificity
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

# S7: Multiple city hiring in same job
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

# S8: Immediate joining / urgent requirements
_IMMEDIATE_JOIN_RE = re.compile(
    r"(?i)(immediate\s*(joining|joiner|requirement|need|position|hire)|"
    r"urgent\s*(requirement|hiring|need|position)|"
    r"join\s*immediately|"
    r"candidates?\s*who\s*can\s*join\s*immediately)"
)

# S16: Walk-in / suspicious hiring keywords in title
_WALKIN_RE = re.compile(
    r"(?i)\b("
    r"walk-?in|walk in|direct joining|urgent(ly)? (hiring|required)|"
    r"mega drive|no interview|bulk hiring|mass recruitment|spot offer"
    r")\b"
)

# S18: Suspicious company name suffix
_COMPANY_SUFFIX_RE = re.compile(
    r"(?i)\b(associates|enterprises|ventures|synergies|manpower|recruiters)\b"
)

# S19: Year number in company name
_DATE_IN_COMPANY_RE = re.compile(
    r"(?i)\b(19|20)\d{2}\b"
)

# S21: Multiple phone numbers in description
_MULTIPLE_PHONES_RE = re.compile(
    r"(?:(?:\+91|91)[\s\-]?)?[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{4}"
)

# S23: Agency "Solutions" naming pattern (e.g., "GIST Management Solutions")
_SOLUTIONS_COMPANY_RE = re.compile(
    r"(?i)^[\w\s]{2,30}\s+(management|career|hr|business|global|job|talent|work)\s+solutions?(?:\s+(?:pvt|private|limited|ltd|inc|corp|llc)){0,2}\s*$"
)

# S24: Work-from-home with unrealistic earning claims
_WFH_SCAM_RE = re.compile(
    r"(?i)(?:work\s*(?:from\s*)?home|online\s*(?:job|work|earning|data\s*entry))"
    r"(?:.*?)(?:lakhs?|crores?|\d{5,}\s*(?:month|salary|earning|income))"
)

# S26: URL shortener / suspicious link in description
_URL_SHORTENER_RE = re.compile(
    r"(?i)\b(bit\.ly|tinyurl|shorturl|short\.link|cutt\.ly|rb\.gy|ow\.ly|is\.gd|"
    r"buff\.ly|shrten|v\.gd|click\.me|shorten\.asia)\b"
)

# ------------------------------------------------------------------
# Helper: Count distinct technology categories
# ------------------------------------------------------------------

def _count_tech_categories(description: str) -> int:
    """Count distinct technology categories in a description (0-5)."""
    desc = description.lower()
    for raw, normalized in _TECH_NORMALIZE.items():
        desc = desc.replace(raw, normalized)
        desc = desc.replace(raw.upper(), normalized)
        desc = desc.replace(raw.capitalize(), normalized)

    categories = 0
    if re.search(r"(?i)\b(python|java|javascript|typescript|go|rust|ruby|php|csharp|cpp|fsharp|scala|kotlin|swift)\b", desc):
        categories += 1
    if re.search(r"(?i)\b(react|angular|vue|svelte|next\.?js|nuxt|sass|html|css|jquery|bootstrap|tailwind)\b", desc):
        categories += 1
    if re.search(r"(?i)\b(django|flask|spring|springboot|fastapi|express|laravel|rails|asp\.net|node\.?js)\b", desc):
        categories += 1
    if re.search(r"(?i)\b(sql|mysql|postgresql|mongodb|redis|oracle|sqlite|mariadb|dynamodb|elasticsearch|cassandra)\b", desc):
        categories += 1
    if re.search(r"(?i)\b(aws|azure|gcp|docker|kubernetes|terraform|jenkins|ansible|cloud|devops|ci/cd)\b", desc):
        categories += 1
    return categories


# ======================================================================
# Domain / Role Matching Helper
# ======================================================================

def is_job_in_excluded_domain(job: Job) -> tuple[bool, str]:
    """
    Check if a job title or company matches fundamentally non-matching domains
    or non-development roles (e.g. QA, support, data entry, medical, design, etc.).

    Returns:
        Tuple of (is_excluded, reason)
    """
    if not job or not job.title:
        return False, ""

    t_lower = job.title.lower()

    non_dev_keywords = [
        ("qa analyst", "QA/Tester role"),
        ("qa engineer", "QA/Tester role"),
        ("qa tester", "QA/Tester role"),
        ("qa ", "QA/Tester role"),
        ("test automation", "Test automation role"),
        ("test engineer", "Test engineering role"),
        ("automation tester", "Automation tester role"),
        ("manual tester", "Manual tester role"),
        ("software tester", "Software tester role"),
        ("etl tester", "ETL tester role"),
        ("tester", "Testing role"),
        ("support engineer", "Support engineering role"),
        ("technical support", "Technical support role"),
        ("customer support", "Customer support role"),
        ("customer care", "Customer care role"),
        ("bpo", "BPO/Call Center role"),
        ("telecaller", "Telecaller role"),
        ("telecalling", "Telecalling role"),
        ("voice process", "Voice process role"),
        ("data entry", "Data entry role"),
        ("data analyst", "Data analyst role"),
        ("business analyst", "Business analyst role"),
        ("business associate", "Business associate role"),
        ("ui designer", "Design role"),
        ("ux designer", "Design role"),
        ("graphic designer", "Design role"),
        ("web designer", "Design role"),
        ("product designer", "Design role"),
        ("animator", "Animation/VFX role"),
        ("vfx", "Animation/VFX role"),
        ("physiotherapist", "Medical/Healthcare role"),
        ("therapist", "Medical/Healthcare role"),
        ("safety database specialist", "Clinical/Medical research role"),
        ("clinical research", "Clinical research role"),
        ("payroll", "HR/Payroll operations role"),
        ("care engineer", "Support/Care role"),
        ("diploma trainee", "Diploma trainee role"),
        ("trs trainee", "Trainee role"),
        ("mechanical", "Non-software engineering role"),
        ("civil engineer", "Civil engineering role"),
        ("electrical engineer", "Electrical engineering role"),
        ("electronics engineer", "Electronics engineering role"),
        ("sales", "Sales role"),
        ("marketing", "Marketing role"),
        ("business development", "Business development role"),
        ("accountant", "Accounting/Finance role"),
        ("accounts", "Accounting/Finance role"),
        ("finance", "Finance role"),
        ("banking", "Banking role"),
        ("auditor", "Auditor role"),
        ("tax", "Taxation role"),
        ("nurse", "Medical/Nursing role"),
        ("doctor", "Medical role"),
        ("pharmacist", "Pharma role"),
        ("chemist", "Pharma role"),
        ("teacher", "Teaching/Faculty role"),
        ("faculty", "Teaching/Faculty role"),
        ("lecturer", "Teaching/Faculty role"),
        ("professor", "Teaching/Faculty role"),
    ]

    for kw, label in non_dev_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", t_lower):
            return True, f"Title indicates non-matching domain/role: {label}"

    return False, ""


# Core Java/JVM stack tokens. Deliberately excludes Kotlin/Scala/Gradle/Maven
# (JVM but not "Java jobs") and generic "backend" (could be any language).
_JAVA_STACK_RE = re.compile(
    r"(?i)\b("
    r"java|j2ee|javaee|jee|jakarta ee|spring|springboot|spring boot|"
    r"hibernate|jsp|servlet|struts|ejb|jdbc|core java|advanced java|"
    r"java developer|java engineer|java backend|java full stack|"
    r"java microservices|spring framework|spring mvc|spring data"
    r")\b"
)


def is_java_related(job: Job) -> tuple[bool, str]:
    """
    Determine whether a job is a Java/Spring role (the user's target stack).

    Returns:
        Tuple of (is_java, reason). True only when the title, skills, or
        description clearly references the Java/JVM + Spring stack.
    """
    if not job:
        return False, "No job provided"

    text = f"{job.title or ''} {job.skills or ''} {job.description or ''}"
    if _JAVA_STACK_RE.search(text):
        return True, "Java/Spring stack detected in posting"

    return False, "No Java/Spring stack found in title, skills, or description"


# ======================================================================
# PHASE 5: Scoring Engine
# ======================================================================

def compute_scam_score(job: Job) -> ScamScoreResult:
    """
    Compute a scam risk score for a job listing using the 5-phase algorithm.

    Args:
        job: The Job entity to evaluate.

    Returns:
        ScamScoreResult with raw_score, display score, reasons list, and level.
    """
    reasons: list[str] = []
    combined_text = f"{job.title} {job.company}" if job.title or job.company else ""
    desc_text = job.description or ""
    normalized_desc = desc_text.lower()
    for raw, normalized in _TECH_NORMALIZE.items():
        normalized_desc = normalized_desc.replace(raw, normalized)
        normalized_desc = normalized_desc.replace(raw.upper(), normalized)
        normalized_desc = normalized_desc.replace(raw.capitalize(), normalized)

    # ------------------------------------------------------------------
    # Phase 1: Genuine Signals (negative points — reduce scam score)
    # ------------------------------------------------------------------
    genuine_deductions = 0
    is_whitelisted = False
    if job.company and _WHITELIST_RE.search(job.company):
        is_whitelisted = True
        genuine_deductions -= 500
        reasons.append("Known reputed company (-500)")

    if job.has_company_logo:
        genuine_deductions -= 30
        reasons.append("Verified company logo (-30)")

    if desc_text:
        tech_match = _TECH_SKILLS_RE.search(normalized_desc)
        tech_categories = _count_tech_categories(normalized_desc)

        if tech_match and tech_categories >= 2 and len(desc_text) > 400:
            genuine_deductions -= 50
            reasons.append(
                f"Detailed technical description with {tech_categories} tech categories (-50)"
            )
        elif tech_match:
            genuine_deductions -= 20
            reasons.append("Technical skills in description (-20)")

    if desc_text and _SALARY_RE.search(desc_text):
        genuine_deductions -= 15
        reasons.append("Salary mentioned in description (-15)")

    # ------------------------------------------------------------------
    # Phases 2-4: Scam Signals
    # ------------------------------------------------------------------
    scam_signals_score = 0
    # critical_score tracks only undeniable-scam signals (agency/overseas/
    # financial/WhatsApp/education-or-generic-services-name/multi-phone).
    # The "force floor to threshold" rule (below) only triggers for these so
    # that medium-risk wording like "freshers advertisement" + "generic
    # description" on a REAL MNC (logo + detailed tech description) can be
    # rescued by genuine deductions instead of being wrongly excluded.
    critical_score = 0

    # S1: Financial scam terms in description (+200)
    if desc_text and _FINANCIAL_SCAM_RE.search(desc_text):
        scam_signals_score += 200
        critical_score += 200
        reasons.append("Financial scam terms in description (+200)")

    # S12a: Agency/consultancy keywords in COMPANY (+200) or TITLE (+100)
    in_company = job.company and _AGENCY_RE.search(job.company)
    in_title = job.title and _AGENCY_RE.search(job.title)
    if in_company:
        scam_signals_score += 200
        critical_score += 200
        reasons.append("Agency/consultancy keywords in company (+200)")
    elif in_title:
        scam_signals_score += 100
        reasons.append("Agency/consultancy keywords in title (+100)")

    # S22a: Overseas/abroad recruiter in company or title (+200)
    overseas_in_company = job.company and _OVERSEAS_RECRUITER_RE.search(job.company)
    overseas_in_title = job.title and _OVERSEAS_RECRUITER_RE.search(job.title)
    overseas_in_desc = desc_text and _OVERSEAS_RECRUITER_RE.search(desc_text)
    if overseas_in_company or overseas_in_title:
        scam_signals_score += 200
        critical_score += 200
        reasons.append("Overseas/abroad job recruiter in company/title (+200)")
    elif overseas_in_desc:
        scam_signals_score += 80
        reasons.append("Overseas/abroad job placement in description (+80)")

    # S2: WhatsApp number in description (+120)
    if desc_text and _WHATSAPP_RE.search(desc_text):
        scam_signals_score += 120
        critical_score += 120
        reasons.append("WhatsApp number in description (+120)")

    # S10: Phone number stuffed in title or company (+100)
    if _PHONE_RE.search(combined_text):
        scam_signals_score += 100
        reasons.append("Phone number in title/company (+100)")

    # S11: Personal email domain in title or company (+100)
    if _EMAIL_RE.search(combined_text):
        scam_signals_score += 100
        reasons.append("Personal email in title/company (+100)")

    # S13: Education/training company name (+120)
    if job.company and _EDUCATION_TRAINING_RE.search(job.company):
        scam_signals_score += 120
        critical_score += 120
        reasons.append("Education/training company name (+120)")

    # S14: Generic services company name (+120)
    if job.company and _GENERIC_SERVICES_RE.search(job.company):
        scam_signals_score += 120
        critical_score += 120
        reasons.append("Generic services company name (+120)")

    # S15: BPO / call-centre / data-entry keywords (+100)
    if _BPO_RE.search(combined_text):
        scam_signals_score += 100
        reasons.append("BPO/staffing keywords (+100)")

    # S17: Hidden / generic company name (+100)
    if job.company and _HIDDEN_COMPANY_RE.match(job.company.strip()):
        scam_signals_score += 100
        reasons.append("Hidden/generic company name (+100)")

    # S21a: Multiple phone numbers in description (+120 / +40)
    if desc_text:
        phone_matches = _MULTIPLE_PHONES_RE.findall(desc_text)
        if len(phone_matches) >= 3:
            scam_signals_score += 120
            critical_score += 120
            reasons.append(f"Multiple phone numbers in description ({len(phone_matches)} found) (+120)")
        elif len(phone_matches) >= 1:
            scam_signals_score += 40
            reasons.append(f"Phone number(s) in description ({len(phone_matches)} found) (+40)")

    # S25: Social media handle in description (+80)
    if desc_text and _SOCIAL_MEDIA_RE.search(desc_text):
        scam_signals_score += 80
        reasons.append("Social media handle in description (+80)")

    # Medium risk signals
    if desc_text and _RESUME_REQUEST_RE.search(desc_text):
        scam_signals_score += 80
        reasons.append("Resume request in description (+80)")

    if desc_text and _CONTACT_HR_RE.search(desc_text):
        scam_signals_score += 60
        reasons.append("Contact HR/recruiter in description (+60)")

    if desc_text and _FRESHERS_AD_RE.search(desc_text):
        scam_signals_score += 70
        reasons.append("Freshers advertisement wording (+70)")

    if desc_text and _GENERIC_DESC_RE.search(desc_text):
        scam_signals_score += 50
        reasons.append("Generic description (soft skills only) (+50)")

    if desc_text and _MULTI_CITY_RE.search(desc_text):
        scam_signals_score += 60
        reasons.append("Multiple city hiring in description (+60)")

    if desc_text and _IMMEDIATE_JOIN_RE.search(desc_text):
        scam_signals_score += 50
        reasons.append("Immediate joining/urgent hiring language (+50)")

    if desc_text and len(desc_text) < 150 and not _TECH_SKILLS_RE.search(normalized_desc):
        scam_signals_score += 60
        reasons.append("Very short description without technical details (+60)")

    if job.title and _WALKIN_RE.search(job.title):
        scam_signals_score += 80
        reasons.append("Walk-in/suspicious hiring keywords (+80)")

    if job.company and _COMPANY_SUFFIX_RE.search(job.company):
        scam_signals_score += 40
        reasons.append("Suspicious company suffix (+40)")

    if job.company and _DATE_IN_COMPANY_RE.search(job.company):
        scam_signals_score += 50
        reasons.append("Year number in company name (+50)")

    if not job.has_company_logo and job.openings >= 30:
        scam_signals_score += 60
        reasons.append("No logo with high openings (+60)")

    if job.company and _SOLUTIONS_COMPANY_RE.match(job.company.strip()):
        scam_signals_score += 80
        reasons.append("Company name matches agency solutions pattern (+80)")

    if desc_text and _WFH_SCAM_RE.search(desc_text):
        scam_signals_score += 60
        reasons.append("Work-from-home with unrealistic earning claims (+60)")

    if desc_text and _URL_SHORTENER_RE.search(desc_text):
        scam_signals_score += 40
        reasons.append("URL shortener in description (+40)")

    raw_score = scam_signals_score + genuine_deductions

    # CRITICAL FIX: The "force floor to threshold" rule only applies when a
    # CRITICAL scam signal fired (agency/overseas/financial/WhatsApp/
    # education-or-generic-services company name / 3+ phones). This prevents a
    # real MNC (verified logo + detailed technical description) from being
    # excluded just because medium-risk wording (e.g. "freshers welcome" +
    # "good communication skills") stacked to >= 80. Genuine deductions are
    # still allowed to pull such listings below threshold. Whititelisted
    # companies (-500) always bypass the floor entirely.
    if not is_whitelisted and critical_score >= SCAM_THRESHOLD:
        raw_score = max(SCAM_THRESHOLD, raw_score)

    display_score = max(0, min(100, raw_score))

    if raw_score >= SCAM_THRESHOLD:
        level = "suspicious"
    elif raw_score >= MODERATE_THRESHOLD:
        level = "moderate"
    else:
        level = "safe"

    return ScamScoreResult(
        score=display_score,
        raw_score=raw_score,
        reasons=reasons,
        level=level,
    )


# ======================================================================
# Specification Pattern Classes
# ======================================================================

class JobSpecification(ABC):
    """
    Base Specification class for evaluating criteria on Job entities.
    Supports logical operators: & (AND), | (OR), and ~ (NOT).
    """

    @abstractmethod
    def is_satisfied_by(self, job: Job) -> bool:
        pass

    def __and__(self, other: JobSpecification) -> JobSpecification:
        return AndSpecification(self, other)

    def __or__(self, other: JobSpecification) -> JobSpecification:
        return OrSpecification(self, other)

    def __invert__(self) -> JobSpecification:
        return NotSpecification(self)


class AndSpecification(JobSpecification):
    """Logical AND composite specification — all sub-specs must match."""

    def __init__(self, *specs: JobSpecification) -> None:
        self._specs = tuple(specs)

    def is_satisfied_by(self, job: Job) -> bool:
        return all(spec.is_satisfied_by(job) for spec in self._specs)


class OrSpecification(JobSpecification):
    """Logical OR composite specification — any sub-spec must match."""

    def __init__(self, *specs: JobSpecification) -> None:
        self._specs = tuple(specs)

    def is_satisfied_by(self, job: Job) -> bool:
        return any(spec.is_satisfied_by(job) for spec in self._specs)


class NotSpecification(JobSpecification):
    """Logical NOT composite specification — inverts the sub-spec."""

    def __init__(self, spec: JobSpecification) -> None:
        self._spec = spec

    def is_satisfied_by(self, job: Job) -> bool:
        return not self._spec.is_satisfied_by(job)


class CompanyExclusionSpecification(JobSpecification):
    """
    Stage 2: Exclude if company name matches the configured blocklist.
    Uses pre-compiled regex for O(N) matching across all blocklist entries.
    """

    def __init__(self, companies: list[str]) -> None:
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
    Stage 2: Exclude if job title contains configured exclusion keywords
    or matches non-matching domain/role patterns.
    """

    def __init__(self, keywords: list[str]) -> None:
        self._regex: re.Pattern[str] | None = None
        if keywords:
            pattern = "|".join(rf"\b{re.escape(k)}\b" for k in keywords)
            self._regex = re.compile(pattern, re.IGNORECASE)

    def is_satisfied_by(self, job: Job) -> bool:
        title = job.title
        if not title:
            return False

        if self._regex and self._regex.search(title):
            logger.info(f"Excluded title match: {title}")
            return True

        is_excl, reason = is_job_in_excluded_domain(job)
        if is_excl:
            logger.info(f"Excluded domain title match: {title} ({reason})")
            return True

        return False


class DescriptionExclusionSpecification(JobSpecification):
    """
    Stage 2: Exclude if job description contains configured exclusion keywords.
    Uses word boundaries for precise matching.
    """

    def __init__(self, keywords: list[str]) -> None:
        self._regex: re.Pattern[str] | None = None
        if keywords:
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
    SCAM_THRESHOLD = SCAM_THRESHOLD

    def is_satisfied_by(self, job: Job) -> bool:
        result = compute_scam_score(job)
        if result.raw_score >= self.SCAM_THRESHOLD:
            reason_str = ", ".join(result.reasons)
            logger.info(
                f"Excluded by Scam Detector v6 (Score: {result.raw_score}): "
                f"{job.title} @ {job.company}. Reasons: {reason_str}"
            )
            return True
        return False


class AuthenticityExclusionSpecification(JobSpecification):
    """
    Stage 3: Evaluate job authenticity based on company identity.
    """

    def __init__(self, blocklist: list[str], max_openings_without_logo: int) -> None:
        self._max_openings = max_openings_without_logo
        self._regex: re.Pattern[str] | None = None
        if blocklist:
            pattern = "|".join(map(re.escape, blocklist))
            self._regex = re.compile(pattern, re.IGNORECASE)

        self._hidden_company_regex = _HIDDEN_COMPANY_RE

    def is_satisfied_by(self, job: Job) -> bool:
        company = job.company

        # 1. Blocked company name
        if company and self._regex and self._regex.search(company):
            logger.info(f"Authenticity Filter: Excluded due to blocked company name: '{company}'")
            return True

        # 2. Hidden/generic company name
        if company and self._hidden_company_regex.match(company.strip()):
            logger.info(
                f"Authenticity Filter: Excluded due to generic/hidden company name: '{company}'"
            )
            return True

        # 3. No logo + high openings
        if not job.has_company_logo and job.openings >= self._max_openings:
            logger.info(
                f"Authenticity Filter: Excluded '{job.title} @ {company}' "
                f"due to high openings ({job.openings}) without a verified company logo."
            )
            return True

        return False


def evaluate_job_all_filters(
    job: Job,
    settings: Any,
    filter_toggles: dict[str, bool] | None = None,
    match_score: float | None = None,
    heuristic_score: float | None = None,
    is_duplicate: bool = False,
) -> dict[str, Any]:
    """
    Evaluates a single job entity against all pipeline filter criteria.
    Supports runtime filter toggles (enable/disable) for real-time debugging.

    Returns a structured dictionary containing overall pass/fail status,
    rejection reasons, and individual filter diagnostics.
    """
    if filter_toggles is None:
        filter_toggles = {}

    # Read toggle overrides or default to settings
    enable_exp = filter_toggles.get("enable_experience_filter", True)
    enable_fresh = filter_toggles.get("enable_freshness_filter", True)
    enable_scam = filter_toggles.get(
        "enable_scam_filter",
        getattr(getattr(settings, "exclusions", None), "enable_scam_filter", True),
    )
    enable_title = filter_toggles.get("enable_title_blacklist", True)
    enable_company = filter_toggles.get("enable_company_blacklist", True)
    enable_desc = filter_toggles.get("enable_description_blacklist", True)
    enable_heuristics = filter_toggles.get(
        "enable_heuristics",
        getattr(getattr(settings, "search", None), "enable_heuristics", True),
    )
    enable_match_score = filter_toggles.get("enable_match_score_filter", True)

    # Master switch check
    master_enabled = filter_toggles.get("master_enable", True)
    if not master_enabled:
        enable_exp = False
        enable_fresh = False
        enable_scam = False
        enable_title = False
        enable_company = False
        enable_desc = False
        enable_heuristics = False
        enable_match_score = False

    search_cfg = getattr(settings, "search", None)
    exclusions_cfg = getattr(settings, "exclusions", None)
    app_cfg = getattr(settings, "application", None)

    max_exp = getattr(search_cfg, "experience_max", 3) if search_cfg else 3
    max_fresh = getattr(search_cfg, "freshness", 30) if search_cfg else 30
    min_match_thresh = (
        getattr(app_cfg, "match_score_threshold", 40.0) if app_cfg else 40.0
    )

    title_keywords = getattr(exclusions_cfg, "title_keywords", []) if exclusions_cfg else []
    companies_bl = getattr(exclusions_cfg, "companies", []) if exclusions_cfg else []
    fake_companies = (
        getattr(exclusions_cfg, "fake_company_blocklist", []) if exclusions_cfg else []
    )
    all_company_bl = list(set(companies_bl + fake_companies))
    desc_keywords = (
        getattr(exclusions_cfg, "description_keywords", []) if exclusions_cfg else []
    )

    evaluations: dict[str, Any] = {}
    rejection_reasons: list[str] = []

    # 1. Experience Filter (check min & max required exp)
    exp_text = str(job.experience or "").lower()
    exp_passed = True
    exp_reason = "Passed"
    if exp_text:
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        if not any(m in exp_text for m in months):
            range_match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", exp_text)
            single_match = re.search(r"(\d+)", exp_text)
            min_req = 0
            max_req = 0
            if range_match:
                min_req = int(range_match.group(1))
                max_req = int(range_match.group(2))
            elif single_match:
                min_req = int(single_match.group(1))
                max_req = min_req

            if min_req > max_exp:
                exp_passed = False
                exp_reason = f"Experience required ({min_req} Yrs) exceeds limit ({max_exp} Yrs)"
            elif max_req > max_exp + 1 and max_req >= 4:
                exp_passed = False
                exp_reason = f"Maximum experience in range ({max_req} Yrs) exceeds target limit ({max_exp} Yrs)"

    evaluations["experience"] = {
        "name": "Experience Limit",
        "enabled": enable_exp,
        "passed": exp_passed,
        "reason": exp_reason,
        "details": {"required": job.experience, "max_allowed": max_exp},
    }
    if enable_exp and not exp_passed:
        rejection_reasons.append(exp_reason)

    # 2. Freshness Filter
    fresh_passed = True
    fresh_reason = "Passed"
    if job.posted_date and max_fresh > 0:
        posted_lower = str(job.posted_date).lower()
        days_old = 0
        if "yesterday" in posted_lower:
            days_old = 1
        elif "week" in posted_lower:
            m = re.search(r"(\d+)", posted_lower)
            days_old = int(m.group(1)) * 7 if m else 7
        elif "month" in posted_lower:
            m = re.search(r"(\d+)", posted_lower)
            days_old = int(m.group(1)) * 30 if m else 30
        elif "day" in posted_lower:
            m = re.search(r"(\d+)", posted_lower)
            days_old = int(m.group(1)) if m else 1
        elif "30+" in posted_lower:
            days_old = 31

        if days_old > max_fresh:
            fresh_passed = False
            fresh_reason = f"Job age (~{days_old} days) exceeds limit ({max_fresh} days)"

    evaluations["freshness"] = {
        "name": "Freshness Limit",
        "enabled": enable_fresh,
        "passed": fresh_passed,
        "reason": fresh_reason,
        "details": {"posted_date": job.posted_date, "max_days": max_fresh},
    }
    if enable_fresh and not fresh_passed:
        rejection_reasons.append(fresh_reason)

    # 3. Scam / Consultancy Detection
    scam_res = compute_scam_score(job)
    scam_passed = scam_res.raw_score < SCAM_THRESHOLD
    scam_reason = (
        f"Scam score {scam_res.raw_score} >= {SCAM_THRESHOLD}"
        if not scam_passed
        else "Passed scam check"
    )

    evaluations["scam_detection"] = {
        "name": "Scam & Consultancy Detection",
        "enabled": enable_scam,
        "passed": scam_passed,
        "score": scam_res.raw_score,
        "threshold": SCAM_THRESHOLD,
        "level": scam_res.level,
        "reasons_list": scam_res.reasons,
        "reason": scam_reason if not scam_passed else f"Scam score: {scam_res.raw_score}",
    }
    if enable_scam and not scam_passed:
        rejection_reasons.append(
            f"Flagged as scam/consultancy (Score: {scam_res.raw_score}): {', '.join(scam_res.reasons[:2])}"
        )

    # 4. Title Blacklist & Non-matching Domain Role Check
    title_passed = True
    matched_title_kws = []
    title_reason = "Passed title check"

    if job.title:
        t_lower = job.title.lower()
        if title_keywords:
            for kw in title_keywords:
                if kw and re.search(r"\b" + re.escape(kw.lower()) + r"\b", t_lower):
                    matched_title_kws.append(kw)

        is_excl_domain, domain_reason = is_job_in_excluded_domain(job)
        if matched_title_kws:
            title_passed = False
            title_reason = f"Title matches blacklisted keyword(s): {', '.join(matched_title_kws)}"
        elif is_excl_domain:
            title_passed = False
            title_reason = domain_reason

    evaluations["title_blacklist"] = {
        "name": "Title Blacklist",
        "enabled": enable_title,
        "passed": title_passed,
        "matched_keywords": matched_title_kws,
        "reason": title_reason,
    }
    if enable_title and not title_passed:
        rejection_reasons.append(title_reason)

    # 5. Company Blacklist & Authenticity Check
    company_passed = True
    matched_company = ""
    company_reason = "Passed company check"

    if job.company:
        c_lower = job.company.lower()
        if all_company_bl:
            for bl_co in all_company_bl:
                if bl_co and bl_co.lower() in c_lower:
                    company_passed = False
                    matched_company = bl_co
                    company_reason = f"Company matches blacklisted term '{matched_company}'"
                    break

        if company_passed and _HIDDEN_COMPANY_RE.match(job.company.strip()):
            company_passed = False
            company_reason = f"Company uses generic/hidden name '{job.company}'"

        max_openings_nologo = getattr(exclusions_cfg, "max_openings_without_logo", 25) if exclusions_cfg else 25
        if company_passed and not job.has_company_logo and (job.openings or 0) >= max_openings_nologo:
            company_passed = False
            company_reason = f"Unverified company without logo posted {job.openings} openings"

    evaluations["company_blacklist"] = {
        "name": "Company Blacklist",
        "enabled": enable_company,
        "passed": company_passed,
        "matched_company": matched_company,
        "reason": company_reason,
    }
    if enable_company and not company_passed:
        rejection_reasons.append(company_reason)

    # 6. Description Blacklist
    desc_passed = True
    matched_desc_kws = []
    if job.description and desc_keywords:
        d_lower = job.description.lower()
        for d_kw in desc_keywords:
            if d_kw and d_kw.lower() in d_lower:
                matched_desc_kws.append(d_kw)
        if matched_desc_kws:
            desc_passed = False
            desc_reason = (
                f"Description contains blacklisted phrase(s): {', '.join(matched_desc_kws[:3])}"
            )
        else:
            desc_reason = "Passed description check"
    else:
        desc_reason = "Passed description check"

    evaluations["description_blacklist"] = {
        "name": "Description Blacklist",
        "enabled": enable_desc,
        "passed": desc_passed,
        "matched_keywords": matched_desc_kws,
        "reason": desc_reason,
    }
    if enable_desc and not desc_passed:
        rejection_reasons.append(desc_reason)

    # 7. Heuristics Filter
    heur_passed = True
    heur_reason = "Passed"
    MIN_HEURISTIC_SCORE = 0.08
    if heuristic_score is not None and heuristic_score < MIN_HEURISTIC_SCORE:
        heur_passed = False
        heur_reason = f"Heuristic score ({heuristic_score:.3f}) below min threshold ({MIN_HEURISTIC_SCORE})"

    evaluations["heuristics"] = {
        "name": "Min Heuristic Score",
        "enabled": enable_heuristics,
        "passed": heur_passed,
        "score": round(heuristic_score, 3) if heuristic_score is not None else None,
        "threshold": MIN_HEURISTIC_SCORE,
        "reason": heur_reason,
    }
    if enable_heuristics and not heur_passed:
        rejection_reasons.append(heur_reason)

    # 8. AI Match Score Threshold
    match_passed = True
    match_reason = "Passed"
    if match_score is not None and match_score < min_match_thresh:
        match_passed = False
        match_reason = f"AI Match Score ({match_score:.1f}) below threshold ({min_match_thresh:.1f})"

    evaluations["match_score"] = {
        "name": "AI Match Score",
        "enabled": enable_match_score,
        "passed": match_passed,
        "score": round(match_score, 1) if match_score is not None else None,
        "threshold": min_match_thresh,
        "reason": match_reason,
    }
    if enable_match_score and not match_passed:
        rejection_reasons.append(match_reason)

    overall_passed = len(rejection_reasons) == 0

    return {
        "passed": overall_passed,
        "rejection_reasons": rejection_reasons,
        "filter_evaluations": evaluations,
    }

