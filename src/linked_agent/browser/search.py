"""
LinkedIn job search module.
Orchestrates search across multiple keywords and locations with pagination.
Uses dict-based dedup (Naukri pattern) so no job is ever missed.

Robust collection features:
  - Session health monitoring between keyword×location combos
  - Dual-mode pagination (URL-based + click-based fallback)
  - Rate limiting detection (429 in URL or page body)
  - Early termination via cross-combo dedup
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.linked_agent.browser.pages.search import LinkedInSearchPage
from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage
from src.linked_agent.config.constants import LINKEDIN_RATE_LIMIT_DELAY
from src.linked_agent.config.settings import Settings
from src.linked_agent.bot.interfaces import IBrowserEngine
from src.linked_agent.models.entities import Job
from src.linked_agent.utils.helpers import LinkedInURLUtility
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)

SESSION_HEARTBEAT_INTERVAL = 180  # seconds between session health checks


class LinkedInJobSearcher:
    """
    Orchestrates LinkedIn job search across multiple keywords and locations.
    Handles pagination and rate limiting.

    Implements the Naukri-style dict-based dedup pattern:
      1. Scrape ALL pages for ALL keyword×location combos FIRST
      2. Store ALL jobs in a dict[str, Job] keyed by linkedin_job_id
      3. Pass the global dict to inner methods for cross-combo dedup
      4. Return list[Job] at the end for downstream processing

    Session health monitoring:
      - Checks login status periodically during long multi-combo searches
      - Pings LinkedIn feed to keep session alive
    """

    def __init__(
        self,
        search_page: LinkedInSearchPage,
        detail_page: LinkedInJobDetailPage,
        engine: IBrowserEngine,
        settings: Settings,
    ) -> None:
        self._search_page = search_page
        self._detail_page = detail_page
        self._engine = engine
        self._settings = settings
        self._last_health_check = 0.0
        self._rate_limited = False

    async def search_all(self) -> list[Job]:
        """
        Search LinkedIn across all configured keyword × location combinations.

        Scrapes ALL pages for ALL combos sequentially, storing every job in a
        global dict[str, Job] keyed by linkedin_job_id (Naukri pattern).

        This ensures:
          - Zero jobs missed (every card on every page is captured)
          - Cross-combo dedup via dict key (if job A appears in both 'Software
            Engineer' and 'Java Developer' searches, it is stored once)
          - Early pagination termination when all results on a page are already
            in the global dict (prevents wasted browsing)

        Returns:
            Flat list[Job] of unique jobs for downstream processing.
        """
        all_jobs: dict[str, Job] = {}

        keywords = self._settings.search.keywords
        locations = self._settings.search.locations
        combo_count = len(keywords) * len(locations)

        for combo_idx, keyword in enumerate(keywords):
            for location in locations:
                logger.info(
                    f"\n[Keyword {combo_idx + 1}/{len(keywords)}] "
                    f"Searching '{keyword}' in '{location}'"
                )

                # Session health check between combos
                await self._check_session_health()

                jobs = await self._search_keyword(
                    keyword=keyword,
                    location=location,
                    seen_ids=all_jobs,
                )

                new_count = 0
                for job in jobs:
                    if job.linkedin_job_id not in all_jobs:
                        all_jobs[job.linkedin_job_id] = job
                        new_count += 1

                logger.info(
                    f"  + {new_count} new jobs from '{keyword}' in '{location}' "
                    f"(total unique: {len(all_jobs)})"
                )

                if self._rate_limited:
                    logger.warning("Rate limited detected — pausing before next combo")
                    await asyncio.sleep(30)
                    self._rate_limited = False

                await asyncio.sleep(LINKEDIN_RATE_LIMIT_DELAY / 1000)

        logger.info(
            f"LinkedIn search complete — all jobs dictionary:\n"
            + "\n".join(
                f"  [{job_id}] {j.title} @ {j.company}"
                for job_id, j in all_jobs.items()
            )
        )
        logger.info(f"Total unique jobs found: {len(all_jobs)}")

        return list(all_jobs.values())

    async def _search_keyword(
        self,
        keyword: str,
        location: str,
        seen_ids: dict[str, Job] | None = None,
    ) -> list[Job]:
        """Search for a specific keyword + location combination with pagination.

        Dual-mode pagination:
          1. URL-based (?start=N) — primary mode, fast and reliable
          2. Click-based (next page button) — fallback when URL redirects to page 1

        Early termination:
          - All jobs on current page are already in query_seen_ids
          - Two consecutive empty or failed pages
          - Pagination redirect detected
        """
        jobs: list[Job] = []
        max_pages = self._settings.search.max_pages
        query_seen_ids: set[str] = set()

        freshness_map = {"any": "", "past_24h": "86400", "past_week": "604800", "past_month": "2592000"}
        freshness = freshness_map.get(self._settings.search.freshness, "604800")

        work_type_map = {"on_site": "1", "remote": "2", "hybrid": "3"}
        work_type = work_type_map.get(self._settings.search.work_type, "") if self._settings.search.work_type else ""

        sort_by = "DD" if self._settings.search.sort_by == "date" else ""
        experience_str = ",".join(self._settings.search.experience_level)

        empty_pages = 0
        use_click_pagination = False  # starts with URL-based
        search_url = ""  # defined in outer scope for click-pagination fallback
        total_results_count: int | None = None
        query_max_pages = max_pages

        for page_num in range(max_pages):
            if page_num >= query_max_pages:
                logger.info(
                    f"Reached max calculated pages ({query_max_pages}) for '{keyword}' in '{location}' — stopping search"
                )
                break

            start = page_num * 25

            if not use_click_pagination:
                search_url = LinkedInURLUtility.build_search_url(
                    keywords=keyword,
                    location=location,
                    freshness=freshness,
                    experience=experience_str,
                    sort_by=sort_by,
                    start=start,
                    work_type=work_type,
                    easy_apply_only=self._settings.application.easy_apply_only,
                )

                logger.info(
                    f"Searching '{keyword}' in '{location}' (page {page_num + 1}/{query_max_pages})"
                )

                try:
                    await self._search_page.navigate_to_search(search_url)

                    # Early check: if page shows "No matching jobs found", stop search immediately
                    if await self._search_page.has_no_results():
                        logger.info(
                            f"Page {page_num + 1} indicates no matching jobs — ending pagination for '{keyword}'"
                        )
                        break

                    # Try to extract total result count to cap max_pages dynamically
                    if total_results_count is None:
                        total_results_count = await self._search_page.get_total_result_count()
                        if total_results_count is not None:
                            import math
                            calc_max = math.ceil(total_results_count / 25)
                            query_max_pages = min(max_pages, max(1, calc_max))
                            logger.info(
                                f"Total results for '{keyword}' in '{location}': {total_results_count} "
                                f"({calc_max} page(s) available, query max capped at {query_max_pages})"
                            )
                            if page_num >= query_max_pages:
                                logger.info(f"Page {page_num + 1} exceeds calculated max pages ({query_max_pages}) — stopping")
                                break

                    # Pagination redirect detection (page 2+ only)
                    if start > 0:
                        current_url = self._engine.page.url
                        parsed_actual = urlparse(current_url)
                        actual_params = parse_qs(parsed_actual.query)
                        actual_start = actual_params.get("start", [None])[0]
                        if actual_start is None or int(actual_start) == 0:
                            logger.warning(
                                f"URL-based pagination redirect detected: start={start} -> "
                                f"actual={actual_start}. Falling back to click-based pagination."
                            )
                            use_click_pagination = True
                            # Retry this page number via click navigation
                            # Re-navigate to page 1 first (to reset the DOM)
                            page1_url = LinkedInURLUtility.build_search_url(
                                keywords=keyword, location=location,
                                freshness=freshness, experience=experience_str,
                                sort_by=sort_by, start=0, work_type=work_type,
                                easy_apply_only=self._settings.application.easy_apply_only,
                            )
                            await self._search_page.navigate_to_search(page1_url)
                            # Click forward to the desired page
                            click_success = True
                            for _ in range(page_num):
                                click_success = await self._search_page.go_to_next_page()
                                if not click_success:
                                    logger.info("Click pagination failed — reached last page")
                                    break
                            if not click_success:
                                break
                            await asyncio.sleep(1)
                            # Use actual page URL as search_url for metadata
                            search_url = self._engine.page.url

                    page_jobs = await self._search_page.parse_job_cards(search_url=search_url)

                except Exception as e:
                    logger.warning(f"Search page {page_num + 1} failed: {e}")
                    empty_pages += 1
                    if empty_pages >= 2:
                        logger.info("Two consecutive failures — stopping pagination")
                        break
                    await asyncio.sleep(3)
                    continue

            else:
                # Click-based pagination fallback
                logger.info(f"Click pagination for '{keyword}' in '{location}' (page {page_num + 1}/{query_max_pages})")
                try:
                    success = await self._search_page.go_to_next_page()
                    if not success:
                        logger.info("No more pages via click pagination")
                        break
                    search_url = self._engine.page.url
                    page_jobs = await self._search_page.parse_job_cards(search_url=search_url)
                except Exception as e:
                    logger.warning(f"Click pagination page {page_num + 1} failed: {e}")
                    empty_pages += 1
                    if empty_pages >= 2:
                        break
                    await asyncio.sleep(3)
                    continue

            # Check for rate limiting in page content
            if await self._detect_rate_limiting(page_jobs):
                self._rate_limited = True
                logger.warning("Rate limiting detected — will pause after this page")
                break

            if not page_jobs:
                logger.info(f"No job results on page {page_num + 1} — stopping search for '{keyword}'")
                break

            empty_pages = 0

            # Within-combo dedup
            new_jobs: list[Job] = []
            for job in page_jobs:
                jid = job.linkedin_job_id or job.url
                if jid not in query_seen_ids:
                    query_seen_ids.add(jid)
                    new_jobs.append(job)

            logger.info(
                f"Page {page_num + 1}: {len(page_jobs)} cards ({len(new_jobs)} new in combo)"
            )

            # Cross-combo dedup — early exit if all seen globally
            if not new_jobs:
                logger.info("All jobs on this page are already globally seen — stopping")
                break

            jobs.extend(new_jobs)

            if page_num < max_pages - 1:
                await asyncio.sleep(LINKEDIN_RATE_LIMIT_DELAY / 1000)

        return jobs

    async def get_job_description(self, job_url: str) -> dict[str, str]:
        """Navigate to a job detail page and extract the full description."""
        success = await self._detail_page.navigate_to_job(job_url)
        if not success:
            return {}

        return await self._detail_page.extract_job_details()

    # ── Session health monitoring ───────────────────────────────────────────

    async def _check_session_health(self) -> None:
        """
        Periodically verify the LinkedIn session is still valid.
        Checks login status indicators every SESSION_HEARTBEAT_INTERVAL seconds.
        """
        now = asyncio.get_event_loop().time()
        if now - self._last_health_check < SESSION_HEARTBEAT_INTERVAL:
            return

        self._last_health_check = now
        logger.info("Performing session health check...")

        try:
            page = self._engine.page
            current_url = page.url
            if "/login" in current_url or "signup" in current_url:
                raise RuntimeError("Session expired — redirected to login page")

            body_text = await page.evaluate(
                "document.body?.innerText?.substring(0, 500) || ''"
            )
            if "sign in" in body_text.lower() or "join now" in body_text.lower():
                logger.warning("Session may have expired — login-related text detected")
            if "captcha" in body_text.lower() or "verify" in body_text.lower():
                raise RuntimeError("CAPTCHA/verification challenge detected")

            # Stay on current page — the heartbeat ping to a static page keeps session alive
            logger.info("Session health check passed")
        except PlaywrightError as e:
            logger.error(f"Session health check failed: {e}")
            raise
        except Exception as e:
            logger.warning(f"Session health check encountered: {e}")

    async def _detect_rate_limiting(self, page_jobs: list[Job]) -> bool:
        """Detect if LinkedIn is rate-limiting by checking page anomalies."""
        if len(page_jobs) > 0:
            return False
        try:
            page = self._engine.page
            body = await page.evaluate(
                "document.body?.innerText?.substring(0, 1000) || ''"
            )
            rate_limit_keywords = [
                "too many requests", "rate limit", "please slow down",
                "try again later", "limite de taux",
            ]
            for kw in rate_limit_keywords:
                if kw in body.lower():
                    return True
        except Exception:
            pass
        return False
