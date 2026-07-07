"""
Filter consultancy, recruiter, and staffing-agency job postings.

Uses Naukri metadata, name heuristics, and optional web search snippets to
reject jobs that are not from a direct software/product employer.
"""

from __future__ import annotations

import asyncio
import json
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

    async def verify_software_employer(self, company: str) -> tuple[bool, str]:
        cache_key = company.strip().lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

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


class DirectEmployerFilter:
    """
    Accept jobs from companies genuinely hiring for themselves.

    Requires a valid company name, rejects consultancy/recruiter posts, and
    optionally requires a company logo on the job post.
    """

    def __init__(
        self,
        *,
        require_direct_employer: bool = True,
        require_company_logo: bool = True,
        min_company_rating_for_logo_fallback: float = 3.0,
    ) -> None:
        self._require_direct_employer = require_direct_employer
        self._require_company_logo = require_company_logo
        self._min_rating_fallback = min_company_rating_for_logo_fallback

    def evaluate(self, job: Job) -> tuple[bool, str]:
        if not self._require_direct_employer:
            return True, ""

        company = (job.company or "").strip()
        if not is_valid_company_name(company):
            return False, "Company name missing or not disclosed"

        is_consultant = job.is_consultant_post
        hiring_for = _clean_label(job.hiring_for)

        if is_consultant is True:
            return False, "Consultancy/recruiter post"

        if hiring_for:
            return False, "Consultancy/recruiter post hiring for client"

        has_logo = job.has_company_logo is True
        is_direct_post = job.is_consultant_post is False
        has_direct_employer_signals = has_logo and is_direct_post

        if not has_direct_employer_signals:
            if _name_looks_like_recruiter(company):
                return False, "Recruiter/staffing agency post"

            if _name_looks_like_consultancy(company):
                return False, "Consultancy posting without direct employer signals"

        if self._require_company_logo:
            if job.has_company_logo is False:
                return False, "No company logo on job post"
            if job.has_company_logo is None:
                has_strong_signals = (
                    job.company_rating is not None
                    and job.company_rating >= self._min_rating_fallback
                    and job.is_verified is True
                )
                if not has_strong_signals:
                    return False, "Company logo status unknown"

        description = (job.description or "").lower()
        if is_consultant is None:
            if "posted by" in description and "consultant" in description:
                return False, "Job description indicates consultant post"
            if re.search(r"\bour client\b", description) and not re.search(
                r"\bclient\s*[:\-]\s*\w", description
            ):
                return False, "Recruiter post references unnamed client"

        return True, ""


class EmployerLegitimacyFilter:
    """Optional online verification for employer legitimacy."""

    def __init__(
        self,
        *,
        verify_online: bool = True,
        web_verifier: CompanyWebVerifier | None = None,
    ) -> None:
        self._verify_online = verify_online
        self._web_verifier = web_verifier or CompanyWebVerifier()

    async def evaluate(self, job: Job) -> tuple[bool, str]:
        if not self._verify_online:
            return True, ""

        company = (job.company or "").strip()
        if not company:
            return False, "Company name missing for online verification"

        return await self._web_verifier.verify_software_employer(company)


class PolicyLegitimacyEvaluator:
    """
    Unified AI-backed legitimacy and relevance evaluator for strict policy mode.
    """

    def __init__(self, llm_provider: Any, *, timeout_seconds: float = 12.0) -> None:
        self._llm_provider = llm_provider
        self._timeout_seconds = timeout_seconds
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    @staticmethod
    def _norm(text: str | None) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _cache_key(self, company: str | None, title: str | None) -> tuple[str, str]:
        return (self._norm(company), self._norm(title))

    async def evaluate(
        self,
        *,
        company: str | None,
        title: str | None,
        description: str | None,
    ) -> dict[str, Any]:
        key = self._cache_key(company, title)
        if key in self._cache:
            return self._cache[key]

        if not key[0] or not key[1]:
            result = {
                "is_legit_company": False,
                "is_post_relevant_to_company": False,
                "confidence": 0.0,
                "reason": "missing company or title",
            }
            self._cache[key] = result
            return result

        prompt = (
            "Return only JSON with keys is_legit_company (bool), "
            "is_post_relevant_to_company (bool), confidence (0 to 1), reason (string).\n"
            "Judge whether company is legitimate and whether this posting is relevant to "
            "that company and title.\n"
            f"Company: {company}\n"
            f"Title: {title}\n"
            f"Description: {(description or '')[:2500]}"
        )
        try:
            raw = await asyncio.wait_for(
                self._llm_provider.generate_content(prompt=prompt, response_mime_type="application/json"),
                timeout=self._timeout_seconds,
            )
            parsed = json.loads(raw)
            result = {
                "is_legit_company": bool(parsed.get("is_legit_company")),
                "is_post_relevant_to_company": bool(parsed.get("is_post_relevant_to_company")),
                "confidence": float(parsed.get("confidence", 0.0)),
                "reason": str(parsed.get("reason", "")).strip() or "no reason provided",
            }
        except Exception as exc:
            result = {
                "is_legit_company": False,
                "is_post_relevant_to_company": False,
                "confidence": 0.0,
                "reason": f"ai_check_failed: {exc}",
            }

        self._cache[key] = result
        return result
