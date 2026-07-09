"""

Naukri.com job search and listing scraper.



Searches for jobs using configured keywords and filters, parses job listing

cards from search results, handles pagination, and navigates to individual

job pages to extract full descriptions.

"""



from __future__ import annotations



import contextlib

from collections.abc import AsyncIterator, Callable

from dataclasses import dataclass



from src.naukri_agent.browser.gate import BrowserGate

from src.naukri_agent.browser.pages.detail import JobDetailPage

from src.naukri_agent.browser.pages.search import SearchPage

from src.naukri_agent.config.settings import Settings

from src.naukri_agent.core.domain.entities import Job

from src.naukri_agent.core.interfaces import IBrowserEngine, IProgressReporter

from src.naukri_agent.core.progress import job_event_payload

from src.naukri_agent.utils.helpers import build_search_url, random_delay

from src.naukri_agent.utils.logger import get_logger, log_info, log_success, log_warning



logger = get_logger(__name__)





@dataclass

class SearchBatch:

    """Jobs discovered for one keyword × location search combination."""



    keyword: str

    location: str

    jobs: list[Job]





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



    async def search_all(self, browser_gate: BrowserGate | None = None) -> list[Job]:

        """

        Search for jobs across all configured keywords and locations.



        Returns:

            List of unique job domain entities.

        """

        all_jobs: list[Job] = []

        async for batch in self.iter_search_batches(browser_gate=browser_gate):

            all_jobs.extend(batch.jobs)

        log_success(f"Total unique jobs found: {len(all_jobs)}")

        return all_jobs



    async def iter_search_batches(

        self,

        browser_gate: BrowserGate | None = None,

    ) -> AsyncIterator[SearchBatch]:

        """

        Yield one batch per keyword × location combination.



        Deduplicates across batches using naukri_job_id. Each batch contains

        only newly discovered unique jobs for that combo.

        """

        seen_ids: set[str] = set()

        search_config = self._settings.search

        log_info(
            f"Search experience filter: {search_config.experience_min}-"
            f"{search_config.experience_max} years"
        )

        for keyword in search_config.keywords:

            for location in search_config.locations:

                if not self._engine.is_alive():

                    log_warning("Browser disconnected! Restarting browser engine...")

                    with contextlib.suppress(Exception):

                        await self._engine.close()

                    await self._engine.launch()



                log_info(f"Searching: '{keyword}' in '{location}'...")



                if browser_gate is not None:

                    async with browser_gate.hold():

                        raw_jobs = await self._search_keyword_location(

                            keyword=keyword,

                            location=location,

                            max_pages=search_config.max_pages,

                        )

                else:

                    raw_jobs = await self._search_keyword_location(

                        keyword=keyword,

                        location=location,

                        max_pages=search_config.max_pages,

                    )



                batch_jobs: list[Job] = []

                for job in raw_jobs:

                    job_id = job.naukri_job_id

                    if job_id and job_id not in seen_ids:

                        seen_ids.add(job_id)

                        batch_jobs.append(job)

                        await self._emit_discovered(job)



                log_success(

                    f"Found {len(raw_jobs)} jobs for '{keyword}' in '{location}' "

                    f"({len(seen_ids)} total unique)"

                )



                yield SearchBatch(keyword=keyword, location=location, jobs=batch_jobs)



                await random_delay(3, 6)



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

                await self._search_page.navigate_to_search(search_url)

                await self._search_page.close_popups()

                await self._search_page.apply_experience_filter(
                    min_exp=self._settings.search.experience_min,
                    max_exp=self._settings.search.experience_max,
                )

                no_results = await self._search_page.has_no_results()

                if no_results:

                    log_warning(f"No results found for page {page_num}")

                    break



                await self._search_page.scroll_to_load()

                jobs_on_page = await self._search_page.parse_job_cards()

                if not jobs_on_page:

                    logger.info(f"No more jobs found on page {page_num}")

                    break



                from src.naukri_agent.utils.filters import JobFilter, JobQualityFilter



                job_filter = JobFilter(
                    min_experience=self._settings.search.experience_min,
                    max_experience=self._settings.search.experience_max,
                    max_freshness_days=self._settings.search.freshness,
                    sort_by=self._settings.search.sort_by,
                )

                quality_filter = JobQualityFilter(

                    require_verified=False,

                    min_company_rating=self._settings.application.min_company_rating,

                )



                filtered_jobs = [

                    job

                    for job in job_filter.filter(jobs_on_page)

                    if quality_filter.should_include_at_search(job)

                ]



                all_jobs.extend(filtered_jobs)

                logger.info(

                    f"Page {page_num}: found {len(filtered_jobs)} valid jobs "

                    f"(filtered out {len(jobs_on_page) - len(filtered_jobs)})"

                )



                await random_delay(2, 5)

            except Exception as e:

                logger.error(f"Error navigating or parsing page {page_num}: {e}")

                break



        return all_jobs



    async def get_job_description(

        self,

        job_url: str,

        browser_gate: BrowserGate | None = None,

    ) -> dict:

        """

        Navigate to a job detail page and extract the full description,

        skills, and other details.

        """

        async def _fetch() -> dict:

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



        if browser_gate is not None:

            async with browser_gate.hold():

                return await _fetch()

        return await _fetch()


