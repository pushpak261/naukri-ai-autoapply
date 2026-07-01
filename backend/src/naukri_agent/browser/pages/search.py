"""
SearchPage Page Object for Naukri.com.
Encapsulates all search listing page actions and scraping evaluation scripts.
"""

from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import Response

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.config.constants import SearchSelectors
from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.naukri_agent.utils.helpers import clean_text, extract_naukri_job_id
from src.naukri_agent.utils.job_metadata import (
    apply_api_metadata,
    parse_dom_metadata,
)
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)

_JOB_CARD_JS = """
() => {
    const jobs = [];
    const cards = document.querySelectorAll(
        '[class*="srp-jobtuple-wrapper"], [class*="jobTuple"], article[class*="job"]'
    );

    for (const card of cards) {
        try {
            const titleElem = card.querySelector('a[class*="title"]');
            if (!titleElem) continue;

            const title = titleElem.innerText.trim();
            let url = titleElem.getAttribute('href') || '';
            if (url && !url.startsWith('http')) {
                url = 'https://www.naukri.com' + url;
            }

            const compElem = card.querySelector('[class*="comp-name"], [class*="companyInfo"] a');
            const company = compElem ? compElem.innerText.trim() : '';

            const locElem = card.querySelector('[class*="loc-wrap"], [class*="location"]');
            const location = locElem ? locElem.innerText.trim() : '';

            const expElem = card.querySelector('[class*="exp-wrap"], [class*="experience"]');
            const experience = expElem ? expElem.innerText.trim() : '';

            const salElem = card.querySelector('[class*="sal-wrap"], [class*="salary"]');
            const salary = salElem ? salElem.innerText.trim() : '';

            const dateElem = card.querySelector('[class*="job-post-day"], [class*="postDate"]');
            const posted_date = dateElem ? dateElem.innerText.trim() : '';

            const tagElems = card.querySelectorAll('[class*="tag-li"], [class*="skill-tag"]');
            const skills = Array.from(tagElems)
                .map(e => e.innerText.trim())
                .filter(Boolean)
                .join(', ');

            let company_rating = null;
            const ratingSelectors = [
                '[class*="ambition"] [class*="rating"]',
                '[class*="rating"]',
                '[class*="star"]',
                '[class*="comp-rating"]',
            ];
            for (const selector of ratingSelectors) {
                const ratingElem = card.querySelector(selector);
                if (!ratingElem) continue;
                const match = (ratingElem.innerText || '').match(/(\\d+(?:\\.\\d+)?)/);
                if (match) {
                    company_rating = parseFloat(match[1]);
                    break;
                }
            }

            let is_verified = null;
            const verifiedSelectors = [
                '[class*="verified"]',
                'img[alt*="Verified" i]',
                '[title*="Verified" i]',
                '[aria-label*="Verified" i]',
            ];
            for (const selector of verifiedSelectors) {
                if (card.querySelector(selector)) {
                    is_verified = true;
                    break;
                }
            }
            if (is_verified === null) {
                const cardText = card.innerText || '';
                if (/\\bverified\\b/i.test(cardText)) {
                    is_verified = true;
                }
            }

            jobs.push({
                title,
                company,
                location,
                experience,
                salary,
                url,
                posted_date,
                skills,
                description: "",
                company_rating,
                is_verified,
            });
        } catch (e) {}
    }
    return jobs;
}
"""


class SearchPage(BasePage):
    """
    Page Object representing the Naukri Job Search Results page.
    """

    def __init__(self, engine: IBrowserEngine, interactions: IBrowserInteractions) -> None:
        super().__init__(engine, interactions)
        self._api_jobs_by_id: dict[str, dict[str, Any]] = {}

    async def navigate_to_search(self, search_url: str) -> None:
        """Navigate to a specific job search URL."""
        page = self._engine.page
        self._api_jobs_by_id = {}
        page.on("response", self._handle_search_response)

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            await self._interactions.wait_for_navigation_complete()
            await asyncio.sleep(2)
        finally:
            page.remove_listener("response", self._handle_search_response)

    async def _handle_search_response(self, response: Response) -> None:
        """Capture Naukri search API payloads for rating / verified metadata."""
        if response.status != 200:
            return
        if "/jobapi/v3/search" not in response.url and "/jobapi/v4/search" not in response.url:
            return

        try:
            data = await response.json()
        except Exception:
            return

        for api_job in data.get("jobDetails", []):
            job_id = str(api_job.get("jobId", "")).strip()
            if job_id:
                self._api_jobs_by_id[job_id] = api_job

    async def has_no_results(self) -> bool:
        """Check if there are no search results on the page."""
        return await self._interactions.element_exists(SearchSelectors.NO_RESULTS)

    async def scroll_to_load(self) -> None:
        """Perform a random scroll to load all dynamic content/cards."""
        await self._interactions.random_scroll(scroll_count=2)

    async def parse_job_cards(self) -> list[Job]:
        """
        Extract all job cards present on the current search results page.
        Executes a Javascript query inside the browser context to parse elements.
        """
        page = self._engine.page
        try:
            raw_jobs = await page.evaluate(_JOB_CARD_JS)

            processed_jobs: list[Job] = []
            for job in raw_jobs:
                if not (job.get("title") and job.get("url")):
                    continue

                naukri_job_id = extract_naukri_job_id(job["url"])
                dom_rating, dom_verified = parse_dom_metadata(job)

                entity = Job(
                    naukri_job_id=naukri_job_id,
                    title=clean_text(job["title"]),
                    company=clean_text(job["company"]),
                    url=job["url"],
                    location=clean_text(job.get("location", "")),
                    experience=clean_text(job.get("experience", "")),
                    salary=clean_text(job.get("salary", "")),
                    description="",
                    skills=clean_text(job.get("skills", "")),
                    posted_date=clean_text(job.get("posted_date", "")),
                    is_verified=dom_verified,
                    company_rating=dom_rating,
                )

                api_job = self._api_jobs_by_id.get(naukri_job_id)
                if api_job:
                    apply_api_metadata(entity, api_job)

                processed_jobs.append(entity)

            logger.debug(
                f"Extracted {len(processed_jobs)} jobs via JS payload "
                f"({len(self._api_jobs_by_id)} API records available)"
            )
            return processed_jobs

        except Exception as e:
            logger.error(f"Failed to parse job cards via JS: {e}")
            return []
