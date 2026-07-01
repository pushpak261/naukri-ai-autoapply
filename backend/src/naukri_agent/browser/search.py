"""
Naukri.com job search and listing scraper.

Searches for jobs using configured keywords and filters, parses job listing
cards from search results, handles pagination, and navigates to individual
job pages to extract full descriptions.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.browser.pages.search import SearchPage
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.core.interfaces import IBrowserEngine, IProgressReporter
from src.naukri_agent.core.progress import job_event_payload
from src.naukri_agent.utils.helpers import build_search_url, random_delay
from src.naukri_agent.utils.logger import get_logger, log_info, log_success, log_warning

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
        self._progress: IProgressReporter | None = None
        self._get_run_id: Callable[[], int | None] | None = None

    def set_progress_reporter(
        self,
        reporter: IProgressReporter,
        get_run_id: Callable[[], int | None],
    ) -> None:
        self._progress = reporter
        self._get_run_id = get_run_id

    async def _emit_discovered(self, job: Job) -> None:
        if not self._progress or not self._get_run_id:
            return
        run_id = self._get_run_id()
        if run_id is None:
            return
        payload = job_event_payload(job, "discovered")
        payload["run_id"] = run_id
        await self._progress.emit("job_updated", payload)

    async def search_all(self) -> list[Job]:
        """
        Search for jobs across all configured keywords and locations.

        Iterates through each keyword × location combination and collects
        job listings up to the configured max_pages per search.

        Returns:
            List of job domain entities.
        """
        all_jobs: list[Job] = []
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
                    job_id = job.naukri_job_id
                    if job_id and job_id not in seen_ids:
                        seen_ids.add(job_id)
                        all_jobs.append(job)
                        await self._emit_discovered(job)

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
    ) -> list[Job]:
        """Search for a specific keyword+location and paginate through results."""
        all_jobs: list[Job] = []

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
                # Navigate via SearchPage PO
                await self._search_page.navigate_to_search(search_url)

                # Close popups
                await self._search_page.close_popups()

                # Check for no results
                no_results = await self._search_page.has_no_results()
                if no_results:
                    log_warning(f"No results found for page {page_num}")
                    break

                # Scroll to load content
                await self._search_page.scroll_to_load()

                # Parse job cards
                jobs_on_page = await self._search_page.parse_job_cards()
                if not jobs_on_page:
                    logger.info(f"No more jobs found on page {page_num}")
                    break

                # Strict client-side filtering to bypass Naukri's ignored URL params
                from src.naukri_agent.utils.filters import JobFilter, JobQualityFilter

                job_filter = JobFilter(
                    max_experience=self._settings.search.experience_max,
                    max_freshness_days=self._settings.search.freshness,
                    sort_by=self._settings.search.sort_by,
                )
                quality_filter = JobQualityFilter(
                    require_verified=self._settings.application.require_verified_job,
                    min_company_rating=self._settings.application.min_company_rating,
                )

                filtered_jobs = [
                    job
                    for job in job_filter.filter(jobs_on_page)
                    if quality_filter.should_include_at_search(job)
                ]

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
        except Exception as e:
            logger.error(f"Failed to get job description from {job_url}: {e}")
            return {
                "description": "",
                "skills": "",
                "experience_detail": "",
                "salary_detail": "",
                "location_detail": "",
                "company_rating": None,
                "is_verified": None,
                "is_external_apply": None,
                "external_apply_url": None,
                "hiring_for": None,
                "is_consultant_post": None,
            }
