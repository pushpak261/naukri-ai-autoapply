"""
Naukri.com job search and listing scraper.

Searches for jobs using configured keywords and filters, parses job listing
cards from search results, handles pagination, and navigates to individual
job pages to extract full descriptions.
"""

from __future__ import annotations

import contextlib

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.browser.pages.search import SearchPage
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job
from src.naukri_agent.bot.interfaces import IBrowserEngine
from src.naukri_agent.utils.helpers import build_search_url, random_delay
from src.naukri_agent.utils.logger import (
    get_logger,
    log_info,
    log_success,
    log_warning,
)

logger = get_logger(__name__)


class JobSearcher:
    """
    Searches Naukri.com for jobs and extracts listing data.

    Usage:
        searcher = JobSearcher(search_page, detail_page, engine, settings)
        jobs = await searcher.search_all()
    """

    def __init__(
        self,
        search_page: SearchPage,
        detail_page: JobDetailPage,
        engine: IBrowserEngine,
        settings: Settings,
    ) -> None:
        self._search_page = search_page
        self._detail_page = detail_page
        self._engine = engine
        self._settings = settings

    async def search_all(self) -> list[Job]:
        """
        Search for jobs across all configured keywords and locations.

        Iterates through each keyword × location combination and collects
        job listings up to the configured max_pages per search.

        Returns:
            List of job domain entities.
        """
        all_jobs: dict[str, Job] = {}

        search_config = self._settings.search

        import asyncio

        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        for keyword in search_config.keywords:
            for location in search_config.locations:
                await queue.put((keyword, location))

        while not queue.empty():
            keyword, location = await queue.get()

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
                seen_ids=all_jobs,
            )

            # Deduplicate
            for job in jobs:
                job_id = job.naukri_job_id
                if job_id and job_id not in all_jobs:
                    all_jobs[job_id] = job

            log_success(
                f"Found {len(jobs)} jobs for '{keyword}' in '{location}' "
                f"({len(all_jobs)} total unique)"
            )

            queue.task_done()

            # Delay between searches if more tasks remain
            if not queue.empty():
                await random_delay(3, 6)

        logger.info(
            f"Final scraped jobs dictionary:\n"
            + "\n".join(
                f"  - '{job_id}': {j.title} @ {j.company}" for job_id, j in all_jobs.items()
            )
        )
        jobs_list = list(all_jobs.values())
        logger.info(
            f"Final scraped jobs list:\n"
            + "\n".join(f"  - {j.title} @ {j.company} (ID: {j.naukri_job_id})" for j in jobs_list)
        )
        log_success(f"Total unique jobs found: {len(all_jobs)}")
        return jobs_list

    async def _search_keyword_location(
        self,
        keyword: str,
        location: str,
        max_pages: int,
        seen_ids: set | dict | None = None,
    ) -> list[Job]:
        """Search for a specific keyword+location and paginate through results."""
        all_jobs: list[Job] = []

        # Bound max_pages defensively to valid pagination limits (1 to 100)
        safe_max_pages = max(1, min(100, max_pages))
        for page_num in range(1, safe_max_pages + 1):
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
                if page_num == 1:
                    # Navigate via SearchPage PO
                    await self._search_page.navigate_to_search(search_url)
                    await self._search_page.close_popups()

                    # Enforce the visual UI slider to fix Naukri's frontend bug
                    await self._search_page.enforce_visual_slider(
                        min_exp=self._settings.search.experience_min,
                        max_exp=self._settings.search.experience_max,
                    )
                else:
                    # Pagination for subsequent pages.
                    # Current SearchPage Page Object does not implement UI click_next_page.
                    # Use URL navigation as the reliable fallback.
                    await self._search_page.navigate_to_search(search_url)
                    await self._search_page.close_popups()

                    # Slider enforcement can help when UI refresh resets it
                    await self._search_page.enforce_visual_slider(
                        min_exp=self._settings.search.experience_min,
                        max_exp=self._settings.search.experience_max,
                    )

                # Check if the page redirected and stripped our search/filter parameters
                current_url = self._engine.page.url
                if "k=" in search_url and "k=" not in current_url:
                    logger.info(
                        f"Search parameters stripped by redirection (Target: {search_url} -> Actual: {current_url}). "
                        f"Likely out-of-bounds page or query reset. Aborting search."
                    )
                    break

                # Check for no results
                no_results = await self._search_page.has_no_results()
                if no_results:
                    log_warning(f"No results found for page {page_num}")
                    break

                # Parse job cards
                jobs_on_page = await self._search_page.parse_job_cards()
                if not jobs_on_page:
                    logger.info(f"No more jobs found on page {page_num}")
                    break

                # Early Pagination Termination check (only after we confirmed we advanced via navigation)
                if seen_ids is not None and len(jobs_on_page) > 0:
                    new_jobs_count = sum(
                        1
                        for j in jobs_on_page
                        if j.naukri_job_id and j.naukri_job_id not in seen_ids
                    )
                    if new_jobs_count == 0:
                        logger.info(
                            f"Page {page_num} yielded 0 new unique jobs (all {len(jobs_on_page)} were already seen). "
                            f"Early termination to save time."
                        )
                        break

                # Strict client-side filtering to bypass Naukri's ignored URL params
                from src.naukri_agent.utils.filters import JobFilter

                job_filter = JobFilter(
                    max_experience=self._settings.search.experience_max,
                    max_freshness_days=self._settings.search.freshness,
                    sort_by=self._settings.search.sort_by,
                )

                filtered_jobs = job_filter.filter(jobs_on_page)

                all_jobs.extend(filtered_jobs)
                logger.info(
                    f"Page {page_num}: found {len(filtered_jobs)} valid jobs (filtered out {len(jobs_on_page) - len(filtered_jobs)})"
                )

                # Delay between pages
                await random_delay(2, 5)
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                logger.error(f"Error navigating or parsing page {page_num}: {e}")
                break

        return all_jobs

    async def get_job_description(self, job_url: str) -> dict:
        """
        Navigate to a job detail page and extract the full description,
        skills, and other details.

        Args:
            job_url: URL of the job detail page.

        Returns:
            Dict with description, skills, and detail fields.
        """
        try:
            await self._detail_page.navigate(job_url)
            await self._detail_page.close_popups()
            return await self._detail_page.get_job_details()
        except (PlaywrightTimeoutError, PlaywrightError) as e:
            logger.error(f"Failed to get job description from {job_url}: {e}")
            return {
                "description": "",
                "skills": "",
                "experience_detail": "",
                "salary_detail": "",
                "location_detail": "",
            }
