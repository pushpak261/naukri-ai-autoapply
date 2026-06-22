"""
Naukri.com job search and listing scraper.

Searches for jobs using configured keywords and filters, parses job listing
cards from search results, handles pagination, and navigates to individual
job pages to extract full descriptions.
"""

from __future__ import annotations

import asyncio
import re

from src.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.config.constants import (
    SearchSelectors,
    JobDetailSelectors,
)
from src.config.settings import Settings
from src.utils.helpers import (
    build_search_url,
    clean_text,
    extract_naukri_job_id,
    random_delay,
)
from src.utils.logger import get_logger, log_info, log_success, log_warning
import contextlib

logger = get_logger(__name__)


class JobSearcher:
    """
    Searches Naukri.com for jobs and extracts listing data.

    Usage:
        searcher = JobSearcher(engine, settings)
        jobs = await searcher.search_all()
    """

    def __init__(
        self, engine: IBrowserEngine, interactions: IBrowserInteractions, settings: Settings
    ) -> None:
        self._engine = engine
        self._interactions = interactions
        self._settings = settings

    async def search_all(self) -> list[dict]:
        """
        Search for jobs across all configured keywords and locations.

        Iterates through each keyword × location combination and collects
        job listings up to the configured max_pages per search.

        Returns:
            List of job data dicts with keys: naukri_job_id, title, company,
            location, experience, salary, url, posted_date, skills, description.
        """
        all_jobs: list[dict] = []
        seen_ids: set = set()

        search_config = self._settings.search

        for keyword in search_config.keywords:
            for location in search_config.locations:
                if not self._engine.is_alive():
                    log_warning("Browser disconnected! Restarting browser engine...")
                    with contextlib.suppress(Exception):
                        await self._engine.close()
                    await self._engine.launch()

                log_info(f"Searching: '{keyword}' in '{location}'...")

                jobs = await self._search_keyword_location(
                    keyword=keyword,
                    location=location,
                    max_pages=search_config.max_pages,
                )

                # Deduplicate
                for job in jobs:
                    job_id = job.get("naukri_job_id", "")
                    if job_id and job_id not in seen_ids:
                        seen_ids.add(job_id)
                        all_jobs.append(job)

                log_success(
                    f"Found {len(jobs)} jobs for '{keyword}' in '{location}' "
                    f"({len(all_jobs)} total unique)"
                )

                # Delay between searches
                await random_delay(3, 6)

        log_success(f"Total unique jobs found: {len(all_jobs)}")
        return all_jobs

    async def _search_keyword_location(
        self,
        keyword: str,
        location: str,
        max_pages: int,
    ) -> list[dict]:
        """Search for a specific keyword+location and paginate through results."""
        all_jobs: list[dict] = []

        for page_num in range(1, max_pages + 1):
            search_url = build_search_url(
                keywords=keyword,
                location=location,
                experience_min=self._settings.search.experience_min,
                experience_max=self._settings.search.experience_max,
                salary_min=self._settings.search.salary_min,
                freshness=self._settings.search.freshness,
                sort_by=self._settings.search.sort_by,
                page=page_num,
            )

            logger.info(f"Searching page {page_num}: {search_url}")

            try:
                page = self._engine.page
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                await self._interactions.wait_for_navigation_complete()
                await asyncio.sleep(2)

                # Close popups
                await self._interactions.close_popups()

                # Check for no results
                no_results = await self._interactions.element_exists(SearchSelectors.NO_RESULTS)
                if no_results:
                    log_warning(f"No results found for page {page_num}")
                    break

                # Scroll to load content
                await self._interactions.random_scroll(scroll_count=2)

                # Parse job cards
                jobs_on_page = await self._parse_job_cards()
                if not jobs_on_page:
                    logger.info(f"No more jobs found on page {page_num}")
                    break

                # Strict client-side filtering to bypass Naukri's ignored URL params
                filtered_jobs = []
                for job in jobs_on_page:
                    exp_text = str(job.get("experience", "")).lower()
                    date_text = str(job.get("posted_date", "")).lower()

                    # 1. Filter by experience
                    skip_exp = False
                    match = re.search(r"(\d+)", exp_text)
                    if match:
                        min_req = int(match.group(1))
                        if min_req > self._settings.search.experience_max:
                            skip_exp = True

                    # 2. Filter by freshness
                    skip_date = False
                    max_days = self._settings.search.freshness
                    if max_days <= 7:
                        # If config says < 7 days, skip anything with weeks/months or 30+
                        if "week" in date_text or "month" in date_text or "30+" in date_text:
                            skip_date = True
                        else:
                            # Extract number of days
                            day_match = re.search(r"(\d+)\s*day", date_text)
                            if day_match and int(day_match.group(1)) > max_days:
                                skip_date = True

                    if not skip_exp and not skip_date:
                        filtered_jobs.append(job)
                    else:
                        logger.debug(
                            f"Strict filter removed: {job.get('title')} (Exp: {exp_text}, Age: {date_text})"
                        )

                all_jobs.extend(filtered_jobs)
                logger.info(
                    f"Page {page_num}: found {len(filtered_jobs)} valid jobs (filtered out {len(jobs_on_page) - len(filtered_jobs)})"
                )

                # Delay between pages
                await random_delay(2, 5)
            except Exception as e:
                logger.error(f"Error navigating or parsing page {page_num}: {e}")
                break

        return all_jobs

    async def _parse_job_cards(self) -> list[dict]:
        """
        Parse all job listing cards on the current search results page.
        Uses a single JS evaluate payload to eliminate Playwright RPC latency.
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

            # Post-process using Python helpers
            processed_jobs = []
            for job in raw_jobs:
                if job.get("title") and job.get("url"):
                    job["naukri_job_id"] = extract_naukri_job_id(job["url"])
                    job["title"] = clean_text(job["title"])
                    job["company"] = clean_text(job["company"])
                    job["location"] = clean_text(job["location"])
                    job["experience"] = clean_text(job["experience"])
                    job["salary"] = clean_text(job["salary"])
                    processed_jobs.append(job)

            logger.debug(f"Extracted {len(processed_jobs)} jobs via JS payload")
            return processed_jobs

        except Exception as e:
            logger.error(f"Failed to parse job cards via JS: {e}")
            return []

    async def get_job_description(self, job_url: str) -> dict:
        """
        Navigate to a job detail page and extract the full description,
        skills, and other details.

        Args:
            job_url: URL of the job detail page.

        Returns:
            Dict with description, skills, and detail fields.
        """
        page = self._engine.page

        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
            await self._interactions.wait_for_navigation_complete()
            await asyncio.sleep(2)

            # Close popups
            await self._interactions.close_popups()

            # Scroll to simulate reading
            await self._interactions.random_scroll(scroll_count=2)

            # Extract description
            description = ""
            desc_elem = await page.query_selector(JobDetailSelectors.JOB_DESCRIPTION)
            if desc_elem:
                description = (await desc_elem.inner_text()) or ""
                description = clean_text(description)

            # Extract skills
            skill_elems = await page.query_selector_all(JobDetailSelectors.KEY_SKILLS)
            skills = []
            for se in skill_elems:
                skill_text = (await se.text_content() or "").strip()
                if skill_text:
                    skills.append(skill_text)

            # Extract detailed fields
            experience = await self._interactions.get_text_content(
                JobDetailSelectors.EXPERIENCE_DETAIL
            )
            salary = await self._interactions.get_text_content(JobDetailSelectors.SALARY_DETAIL)
            location = await self._interactions.get_text_content(JobDetailSelectors.LOCATION_DETAIL)

            return {
                "description": description,
                "skills": ", ".join(skills),
                "experience_detail": clean_text(experience),
                "salary_detail": clean_text(salary),
                "location_detail": clean_text(location),
            }

        except Exception as e:
            logger.error(f"Failed to get job description from {job_url}: {e}")
            return {
                "description": "",
                "skills": "",
                "experience_detail": "",
                "salary_detail": "",
                "location_detail": "",
            }

