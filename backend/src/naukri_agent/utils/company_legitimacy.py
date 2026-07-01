"""
Filter consultancy, recruiter, and staffing-agency job postings.

Uses Naukri metadata, name heuristics, and optional web search snippets to
reject jobs that are not from a direct software/product employer.
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from src.naukri_agent.core.domain.entities import Job

logger = logging.getLogger(__name__)

_INVALID_COMPANY_NAMES = frozenset(
    {
        "",
        "not disclosed",
        "confidential",
        "company not disclosed",
        "hidden",
        "na",
        "n/a",
        "-",
        "unknown",
    }
)

_RECRUITER_NAME_PATTERN = re.compile(
    r"\b("
    r"staffing|recruitment|recruiter|recruiting|placement|placements|"
    r"manpower|headhunter|talent\s+solutions|hr\s+solutions|"
    r"job\s+consult|consultancy\s+services|hiring\s+partner|"
    r"executive\s+search|workforce\s+solutions|staff\s+augmentation"
    r")\b",
    re.IGNORECASE,
)

_CONSULTANCY_NAME_PATTERN = re.compile(
    r"\b("
    r"consultancy|consulting\s+(firm|company|services)|"
    r"it\s+services\s+partner|outsourcing\s+partner"
    r")\b",
    re.IGNORECASE,
)

_STAFFING_WEB_PATTERN = re.compile(
    r"\b("
    r"staffing|recruitment\s+agency|recruiting\s+firm|placement\s+agency|"
    r"manpower\s+consult|headhunter|talent\s+acquisition\s+firm|"
    r"job\s+consultancy|hiring\s+agency|executive\s+search"
    r")\b",
    re.IGNORECASE,
)

_SOFTWARE_EMPLOYER_WEB_PATTERN = re.compile(
    r"\b("
    r"software\s+company|technology\s+company|product\s+company|"
    r"saas|fintech|it\s+services|tech\s+company|engineering\s+company|"
    r"multinational\s+corporation|mnc|fortune\s+\d+"
    r")\b",
    re.IGNORECASE,
)


def _clean_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in _INVALID_COMPANY_NAMES:
        return None
    return text


def is_valid_company_name(company: str | None) -> bool:
    if not company:
        return False
    return company.strip().lower() not in _INVALID_COMPANY_NAMES


def company_matches_allowlist(company: str, allowlist: list[str]) -> bool:
    if not company or not allowlist:
        return False
    company_lower = company.lower()
    return any(entry.strip().lower() in company_lower for entry in allowlist if entry.strip())


def _name_looks_like_recruiter(company: str) -> bool:
    return bool(_RECRUITER_NAME_PATTERN.search(company))


def _name_looks_like_consultancy(company: str) -> bool:
    return bool(_CONSULTANCY_NAME_PATTERN.search(company))


def _fetch_web_snippets_sync(query: str, timeout: float = 8.0) -> str:
    """Fetch DuckDuckGo HTML results and return concatenated snippet text."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NaukriAgent/1.0)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.debug("Web search failed for %r: %s", query, exc)
        return ""

    snippets: list[str] = []
    for match in re.finditer(
        r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        text = re.sub(r"<[^>]+>", " ", match.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            snippets.append(text)
        if len(snippets) >= 5:
            break

    if not snippets:
        plain = re.sub(r"<[^>]+>", " ", html)
        snippets = [plain[:2000]]

    return " ".join(snippets)


class CompanyWebVerifier:
    """Caches lightweight web lookups used to distinguish employers from agencies."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[bool, str]] = {}

    async def verify_software_employer(
        self,
        company: str,
        *,
        allowlisted: bool = False,
    ) -> tuple[bool, str]:
        cache_key = company.strip().lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if allowlisted:
            result = (True, "Company is in big_companies allowlist")
            self._cache[cache_key] = result
            return result

        query = f'"{company}" software technology company'
        snippets = await asyncio.to_thread(_fetch_web_snippets_sync, query)
        if not snippets:
            result = (False, "Could not verify employer online")
            self._cache[cache_key] = result
            return result

        staffing_hits = len(_STAFFING_WEB_PATTERN.findall(snippets))
        employer_hits = len(_SOFTWARE_EMPLOYER_WEB_PATTERN.findall(snippets))

        company_in_snippets = company.lower() in snippets.lower()
        if staffing_hits > employer_hits and staffing_hits > 0:
            result = (
                False,
                "Web search indicates staffing/recruitment agency, not direct employer",
            )
        elif employer_hits > 0 and company_in_snippets:
            result = (True, "Web search indicates direct technology employer")
        elif employer_hits > staffing_hits:
            result = (True, "Web search suggests legitimate technology employer")
        else:
            result = (
                False,
                "Could not confirm company as a direct software employer online",
            )

        self._cache[cache_key] = result
        return result


class EmployerLegitimacyFilter:
    """
    Reject consultancy/recruiter postings and unverified employer names.

    Rules (in order):
    1. Missing or undisclosed company name → reject
    2. Consultant/recruiter post without named hiring company → reject
    3. Company name matches recruiter/staffing patterns (non-allowlisted) → reject
    4. Optional online verification for non-allowlisted names
    """

    def __init__(
        self,
        *,
        big_companies: list[str] | None = None,
        verify_online: bool = True,
        web_verifier: CompanyWebVerifier | None = None,
    ) -> None:
        self._big_companies = big_companies or []
        self._verify_online = verify_online
        self._web_verifier = web_verifier or CompanyWebVerifier()

    def evaluate_sync(self, job: Job) -> tuple[bool, str]:
        """Synchronous heuristic checks (no web lookup)."""
        company = (job.company or "").strip()
        if not is_valid_company_name(company):
            return False, "Company name missing or not disclosed"

        hiring_for = _clean_label(getattr(job, "hiring_for", None))
        is_consultant = getattr(job, "is_consultant_post", None)
        looks_like_recruiter = _name_looks_like_recruiter(company)
        allowlisted = company_matches_allowlist(company, self._big_companies) and not looks_like_recruiter

        if is_consultant is True and not hiring_for:
            return False, "Consultant posting without named hiring company"

        if looks_like_recruiter:
            if not hiring_for:
                return False, "Recruiter/staffing agency without hiring company information"

        if _name_looks_like_consultancy(company) and not allowlisted and not hiring_for:
            return False, "Consultancy posting without named end client"

        description = (job.description or "").lower()
        if is_consultant is None and not hiring_for:
            if "posted by" in description and "consultant" in description:
                return False, "Job description indicates consultant post without client"
            if re.search(r"\bour client\b", description) and not re.search(
                r"\bclient\s*[:\-]\s*\w", description
            ):
                return False, "Recruiter post references unnamed client"

        return True, ""

    async def evaluate(self, job: Job) -> tuple[bool, str]:
        passes, reason = self.evaluate_sync(job)
        if not passes:
            return passes, reason

        company = job.company.strip()
        hiring_for = _clean_label(job.hiring_for)
        looks_like_recruiter = _name_looks_like_recruiter(company)
        allowlisted = company_matches_allowlist(company, self._big_companies) and not looks_like_recruiter

        if not self._verify_online:
            return True, ""

        if allowlisted:
            return True, ""

        verify_name = hiring_for or company
        return await self._web_verifier.verify_software_employer(
            verify_name,
            allowlisted=False,
        )
