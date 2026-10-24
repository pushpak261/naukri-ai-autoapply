"""
Naukri.com job search and listing scraper.

Searches for jobs using configured keywords and filters, parses job listing
cards from search results, handles pagination, and navigates to individual
job pages to extract full descriptions.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.browser.pages.search import SearchPage
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job
from src.naukri_agent.bot.interfaces import IBrowserEngine
from src.naukri_agent.utils.helpers import build_search_url, random_delay
from src.naukri_agent.utils.exceptions import SearchAccessError, SearchLoadError
from src.naukri_agent.utils.logger import (
    get_logger,
    log_info,
    log_success,
    log_warning,
)

logger = get_logger(__name__)


def _same_search_page(requested_url: str, current_url: str) -> bool:
    """Allow canonical URLs only when the query and pagination context survive."""
    requested, current = urlsplit(requested_url), urlsplit(current_url)
    allowed_hosts = {"naukri.com", "www.naukri.com"}
    if current.scheme != "https" or current.hostname not in allowed_hosts:
        return False
    if current.path.rstrip("/") != requested.path.rstrip("/"):
        return False
    requested_query = parse_qs(requested.query, keep_blank_values=True)
    current_query = parse_qs(current.query, keep_blank_values=True)
    # Keywords, location and page are also encoded in our route. Missing query
    # values are safe on that same route; conflicting values mean a query reset.
    return all(
        key not in current_query or current_query[key] == requested_query.get(key)
        for key in ("k", "l", "pageNo")
    )


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
        repository=None,
    ) -> None:
        self._search_page = search_page
        self._detail_page = detail_page
        self._engine = engine
        self._settings = settings
        self._repository = repository
        self._discovered_ids: set[str] = set()
        # Running count of unique jobs discovered so far. Exposed so the
        # orchestrator can report an accurate total even when the search is
        # interrupted mid-way (e.g. by a shutdown signal).
        self.total_found: int = 0
        self.failed_searches: list[str] = []

    async def search_all(
        self, should_stop: Callable[[], bool] | None = None
    ) -> list[Job]:
        """
        Search for jobs across all configured keywords and locations.

        Iterates through each keyword × location combination and collects
        job listings up to the configured max_pages per search.
        The application cap limits submissions, not discovery. Search every
        configured combination so later locations and better matches are kept.

        Args:
            should_stop: Optional callable evaluated before each search step.
                When it returns True (e.g. a shutdown signal was received),
                the search stops gracefully and returns the jobs collected so
                far instead of raising or retrying against a dead browser.

        Returns:
            List of job domain entities (partial on interruption).
        """
        all_jobs: dict[str, Job] = {}
        self._discovered_ids.clear()
        self.total_found = 0
        self.failed_searches.clear()
        consecutive_failures = 0

        search_config = self._settings.search

        import asyncio

        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        for keyword in search_config.keywords:
            for location in search_config.locations:
                await queue.put((keyword, location))

        while not queue.empty():
            if should_stop and should_stop():
                log_info("Shutdown requested — stopping search early.")
                break

            keyword, location = await queue.get()

            if not self._engine.is_alive():
                log_warning("Browser disconnected! Restarting browser engine...")
                with contextlib.suppress(Exception):
                    await self._engine.close()
                await self._engine.launch()

            log_info(f"Searching: '{keyword}' in '{location}'...")

            try:
                jobs = await self._search_keyword_location(
                    keyword=keyword,
                    location=location,
                    max_pages=search_config.max_pages,
                    seen_ids=all_jobs,
                    should_stop=should_stop,
                )
            except SearchAccessError:
                raise
            except Exception as e:
                self.failed_searches.append(f"{keyword} in {location}")
                consecutive_failures += 1
                logger.error(f"Search for '{keyword}' in '{location}' failed: {e}")
                if isinstance(e, SearchLoadError) and consecutive_failures >= 2:
                    raise SearchLoadError("Naukri failed to load consecutive searches after retries; stopping discovery instead of reporting zero matches.") from e
                if (should_stop and should_stop()) or not self._engine.is_alive():
                    log_warning("Search interrupted — returning partial results.")
                    break
                log_warning("Search failed for this combination; continuing with the remaining searches.")
                queue.task_done()
                continue

            consecutive_failures = 0

            # Deduplicate
            for job in jobs:
                job_id = job.naukri_job_id
                if job_id and job_id not in all_jobs:
                    all_jobs[job_id] = job

            self.total_found = len(all_jobs)

            log_success(
                f"Found {len(jobs)} jobs for '{keyword}' in '{location}' "
                f"({len(all_jobs)} total unique)"
            )

            queue.task_done()

            # Delay between searches if more tasks remain
            if not queue.empty():
                await random_delay(3, 6)

        logger.debug(
            "Final scraped jobs dictionary:\n"
            + "\n".join(
                f"  - '{job_id}': {j.title} @ {j.company}" for job_id, j in all_jobs.items()
            )
        )
        jobs_list = list(all_jobs.values())
        if self.failed_searches and not jobs_list:
            raise SearchLoadError(f"{len(self.failed_searches)} searches failed; no verified search results were obtained.")
        logger.debug(
            "Final scraped jobs list:\n"
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
        should_stop: Callable[[], bool] | None = None,
    ) -> list[Job]:
        """Search for a specific keyword+location and paginate through results."""
        all_jobs: list[Job] = []

        # Bound max_pages defensively to valid pagination limits (1 to 100)
        query_seen_ids = set()
        safe_max_pages = max(1, min(100, max_pages))
        for page_num in range(1, safe_max_pages + 1):
            if should_stop and should_stop():
                log_info("Shutdown requested — stopping pagination early.")
                break

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
                # Navigate via SearchPage PO. URL navigation is also the reliable
                # fallback for pagination, because the SearchPage page object does
                # not implement click_next_page.
                await self._search_page.navigate_to_search(search_url)
                await self._search_page.close_popups()

                # Naukri can canonicalize a valid search by stripping its query
                # string. Verify the route before parsing rather than discarding
                # that page. Local experience/freshness filters still run below.
                current_url = self._engine.page.url
                if not _same_search_page(search_url, current_url):
                    logger.warning(
                        "Search redirected outside the requested query/page; stopping this search "
                        "without collecting unrelated results (requested: %s, actual: %s).",
                        search_url, current_url,
                    )
                    break
                if "k=" in search_url and "k=" not in current_url:
                    logger.info(
                        "Search query string removed on the same route; checking results with local filters."
                    )

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
                if len(jobs_on_page) > 0:
                    new_jobs_count = sum(
                        1
                        for j in jobs_on_page
                        if j.naukri_job_id and j.naukri_job_id not in query_seen_ids
                    )
                    if new_jobs_count == 0:
                        logger.info(
                            f"Page {page_num} yielded 0 new unique jobs for this query (all {len(jobs_on_page)} were already seen). "
                            f"Early termination to prevent pagination loop."
                        )
                        break

                    # Update query seen set
                    for j in jobs_on_page:
                        if j.naukri_job_id:
                            query_seen_ids.add(j.naukri_job_id)

                # Strict client-side filtering to bypass Naukri's ignored URL params
                from src.naukri_agent.utils.filters import JobFilter

                job_filter = JobFilter(
                    max_experience=self._settings.search.experience_max,
                    max_freshness_days=self._settings.search.freshness,
                    sort_by=self._settings.search.sort_by,
                )

                filtered_jobs = job_filter.filter(jobs_on_page)

                # Persist each completed page so stopping during discovery does
                # not discard every listing collected by the run.
                for job in filtered_jobs:
                    if job.naukri_job_id in self._discovered_ids:
                        continue
                    if self._repository is not None:
                        import dataclasses
                        fields = dataclasses.asdict(job)
                        fields.pop("id", None)
                        fields.pop("scraped_at", None)
                        saved = await self._repository.save_job(**fields)
                        job.id = saved.id
                    self._discovered_ids.add(job.naukri_job_id)
                self.total_found = len(self._discovered_ids)

                all_jobs.extend(filtered_jobs)
                logger.info(
                    f"Page {page_num}: found {len(filtered_jobs)} valid jobs (filtered out {len(jobs_on_page) - len(filtered_jobs)})"
                )

                # Delay between pages
                await random_delay(2, 5)
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                logger.error(f"Error navigating or parsing page {page_num}: {e}")
                if not all_jobs:
                    raise SearchLoadError(f"Failed to read search page {page_num}.") from e
                self.failed_searches.append(f"{keyword} in {location}, page {page_num}")
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
