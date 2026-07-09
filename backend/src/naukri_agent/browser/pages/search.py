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

            let has_company_logo = null;
            const isValidLogoSrc = (src) => {
                if (!src || typeof src !== 'string') return false;
                const trimmed = src.trim();
                if (!trimmed || trimmed === '#' || trimmed.startsWith('data:image/svg')) return false;
                const lower = trimmed.toLowerCase();
                if (/placeholder|default|no-?logo|generic|blank|dummy|avatar/.test(lower)) return false;
                return /\\.(png|jpe?g|webp|svg|gif)(\\?|$)/i.test(lower) || (lower.includes('logo') && !lower.includes('naukri'));
            };
            const logoSelectors = [
                '[class*="comp-logo"] img',
                '[class*="company-logo"] img',
                '[class*="comp-name"] img',
                '[class*="companyInfo"] img',
                'img[class*="comp-logo"]',
                'img[class*="company-logo"]',
            ];
            for (const selector of logoSelectors) {
                const logoElem = card.querySelector(selector);
                if (!logoElem) continue;
                const src = logoElem.getAttribute('src') || logoElem.getAttribute('data-src') || '';
                if (isValidLogoSrc(src)) {
                    has_company_logo = true;
                    break;
                }
            }
            if (has_company_logo === null) {
                for (const selector of logoSelectors) {
                    if (card.querySelector(selector)) {
                        has_company_logo = false;
                        break;
                    }
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
                has_company_logo,
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

    async def apply_experience_filter(self, min_exp: int, max_exp: int) -> None:
        """
        Apply the configured experience range on Naukri's search filter UI.

        Naukri often ignores `experiencemax` in the URL; setting the filter in the
        sidebar ensures search results match the configured min/max years.
        """
        page = self._engine.page
        try:
            min_exp = int(min_exp)
            max_exp = int(max_exp)
        except (TypeError, ValueError):
            return

        if max_exp <= min_exp:
            max_exp = min_exp + 1

        try:
            exp_heading = page.locator(
                'xpath=//*[self::span or self::div or self::label]'
                '[contains(normalize-space(.), "Experience") and string-length(normalize-space(.)) < 24]'
            ).first
            if await exp_heading.count() > 0:
                await exp_heading.click(timeout=3000)
                await asyncio.sleep(0.4)

            applied = await page.evaluate(
                """([minExp, maxExp]) => {
                    const dispatch = (el) => {
                        el.dispatchEvent(new Event("input", { bubbles: true }));
                        el.dispatchEvent(new Event("change", { bubbles: true }));
                    };

                    const containers = document.querySelectorAll(
                        '[class*="slider-container"], [class*="slider-labels"], [class*="experience"]'
                    );
                    for (const container of containers) {
                        const ranges = container.querySelectorAll('input[type="range"]');
                        if (ranges.length >= 2) {
                            ranges[0].value = String(minExp);
                            ranges[1].value = String(maxExp);
                            dispatch(ranges[0]);
                            dispatch(ranges[1]);
                            return true;
                        }
                        if (ranges.length === 1) {
                            ranges[0].value = String(minExp);
                            dispatch(ranges[0]);
                            return true;
                        }
                    }

                    const minInput = document.querySelector(
                        'input[name*="min" i][name*="exp" i], input[placeholder*="Min" i]'
                    );
                    const maxInput = document.querySelector(
                        'input[name*="max" i][name*="exp" i], input[placeholder*="Max" i]'
                    );
                    if (minInput && maxInput) {
                        minInput.value = String(minExp);
                        maxInput.value = String(maxExp);
                        dispatch(minInput);
                        dispatch(maxInput);
                        return true;
                    }
                    return false;
                }""",
                [min_exp, max_exp],
            )

            if applied:
                apply_btn = page.locator(
                    'button:has-text("Apply"), button:has-text("View Jobs"), button:has-text("Apply Filters")'
                ).first
                if await apply_btn.count() > 0:
                    await apply_btn.click(timeout=5000)
                    await self._interactions.wait_for_navigation_complete()
                    await asyncio.sleep(1)
                logger.info(f"Applied Naukri experience filter: {min_exp}-{max_exp} years")
            else:
                logger.debug(
                    "Experience filter controls not found on page; "
                    "using URL params and client-side filtering"
                )

            await self.enforce_visual_slider(min_exp, max_exp)
        except Exception as e:
            logger.debug(f"Could not apply experience filter via UI: {e}")

    async def enforce_visual_slider(self, min_exp: int, max_exp: int) -> None:
        """Reflect the configured experience range in Naukri's filter label UI."""
        page = self._engine.page
        try:
            js_payload = f"""
                (() => {{
                    const sliderContainers = document.querySelectorAll(
                        '.styles_slider-container__2M_h3, .styles_slider-labels, .slider-label'
                    );
                    sliderContainers.forEach(container => {{
                        if (container.innerText.includes('Yrs') || container.innerText.includes('Any')) {{
                            container.innerHTML = '<b>{min_exp} Yrs - {max_exp} Yrs</b>';
                            container.style.color = '#ff6c00';
                            container.style.fontSize = '14px';
                            container.title = 'Agent Override Active';
                        }}
                    }});
                }})();
            """
            await page.evaluate(js_payload)
        except Exception as e:
            logger.debug(f"Failed to enforce visual slider: {e}")

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
                dom_rating, dom_verified, dom_logo = parse_dom_metadata(job)

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
                    has_company_logo=dom_logo,
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
