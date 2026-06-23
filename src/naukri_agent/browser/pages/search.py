"""
SearchPage Page Object for Naukri.com.
Encapsulates all search listing page actions and scraping evaluation scripts.
"""

from __future__ import annotations

import asyncio

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.config.constants import SearchSelectors
from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.utils.helpers import clean_text, extract_naukri_job_id
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


class SearchPage(BasePage):
    """
    Page Object representing the Naukri Job Search Results page.
    """

    async def navigate_to_search(self, search_url: str) -> None:
        """Navigate to a specific job search URL."""
        page = self._engine.page
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        await self._interactions.wait_for_navigation_complete()
        await asyncio.sleep(2)

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
            # Run extraction entirely within the browser context for speed
            js_script = """
            () => {
                const jobs = [];
                const cards = document.querySelectorAll('[class*="srp-jobtuple-wrapper"], [class*="jobTuple"], article[class*="job"]');
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
                        const skills = Array.from(tagElems).map(e => e.innerText.trim()).filter(Boolean).join(', ');

                        jobs.push({
                            title: title,
                            company: company,
                            location: location,
                            experience: experience,
                            salary: salary,
                            url: url,
                            posted_date: posted_date,
                            skills: skills,
                            description: ""
                        });
                    } catch (e) {}
                }
                return jobs;
            }
            """
            raw_jobs = await page.evaluate(js_script)

            processed_jobs: list[Job] = []
            for job in raw_jobs:
                if job.get("title") and job.get("url"):
                    naukri_job_id = extract_naukri_job_id(job["url"])
                    processed_jobs.append(
                        Job(
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
                        )
                    )

            logger.debug(f"Extracted {len(processed_jobs)} jobs via JS payload in Page Object")
            return processed_jobs

        except Exception as e:
            logger.error(f"Failed to parse job cards via JS: {e}")
            return []
