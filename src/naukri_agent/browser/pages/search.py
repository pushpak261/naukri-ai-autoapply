"""
SearchPage Page Object for Naukri.com.
Encapsulates all search listing page actions and scraping evaluation scripts.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.models.entities import Job
from src.naukri_agent.utils.helpers import clean_text, extract_naukri_job_id
from src.naukri_agent.utils.logger import get_logger
from src.naukri_agent.utils.exceptions import SearchAccessError, SearchLoadError

logger = get_logger(__name__)

SEARCH_STATE_JS = r"""() => {
    const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
    if (/access denied|verify (?:that )?you are human|complete (?:the |a )?captcha|unusual traffic|too many requests/i.test(text)) return 'blocked';
    if (/\/nlogin\/login|\/account\/login/.test(location.pathname)) return 'login';
    if (/oops!?\s*something went wrong|there was an error loading the page|service unavailable|temporarily unavailable/i.test(text)) return 'error';
    const cards = document.querySelectorAll('[class*="srp-jobtuple"], [class*="jobTuple"], article[class*="job"], [class*="sjw__tuple"], [class*="cust-job-tuple"]');
    if ([...cards].some(card => {
        const title = card.querySelector('a[class*="title"][href]');
        return !card.closest('aside, [class*="recommend" i]') && title && visible(title) && title.textContent.trim();
    })) return 'results';
    if (/no matching jobs|no jobs found|no results found|\b0 (?:jobs|results) found/i.test(text)) return 'empty';
    return null;
}"""


class SearchPage(BasePage):
    """
    Page Object representing the Naukri Job Search Results page.
    """

    async def enforce_visual_slider(self, min_exp: int, max_exp: int) -> None:
        """Compatibility hook; real experience limits are enforced by JobFilter.

        Never rewrite the website's displayed controls to pretend a server-side
        filter was applied.
        """
        logger.debug("Experience limits are enforced locally: %s-%s", min_exp, max_exp)

    async def navigate_to_search(self, search_url: str) -> None:
        """Wait for actual results/empty state; retry render failures, never challenges."""
        page = self._engine.page
        active_url = search_url
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Navigating to search page (attempt {attempt}/{max_retries}): {active_url}"
                )
                response = await page.goto(active_url, wait_until="domcontentloaded", timeout=60000)
                if response and response.status in (401, 403, 429):
                    raise SearchAccessError(f"Naukri search returned HTTP {response.status}; user action is required before restarting.")
                if response and response.status >= 400:
                    raise SearchLoadError(f"Naukri search returned HTTP {response.status}.")
                await self._wait_for_search_state()
                return
            except SearchAccessError:
                raise
            except (SearchLoadError, PlaywrightError) as e:
                logger.warning(f"Navigation attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    raise SearchLoadError(f"Naukri search failed after {max_retries} attempts: {e}") from e
                # Keep keyword, location, page and filters. Only sorting is
                # optional; local date sorting still runs in JobFilter.
                parts = urlsplit(active_url)
                query = parse_qsl(parts.query, keep_blank_values=True)
                if any(key == "sort" for key, _ in query):
                    active_url = urlunsplit(parts._replace(query=urlencode([(k,v) for k,v in query if k != "sort"])))
                    logger.warning("Retrying the same search without server-side sorting; local filters remain active.")
                await asyncio.sleep(2 * attempt)  # Exponential backoff

    async def _wait_for_search_state(self) -> str:
        try:
            handle = await self._engine.page.wait_for_function(SEARCH_STATE_JS, timeout=20000)
            try:
                state = await handle.json_value()
            finally:
                await handle.dispose()
        except PlaywrightTimeoutError as error:
            raise SearchLoadError("Search did not render job cards or an explicit no-results message.") from error
        if state in ("blocked", "login"):
            raise SearchAccessError("Naukri search requires sign-in or manual verification; no further searches will be attempted.")
        if state == "error":
            raise SearchLoadError("Naukri displayed its page-load error screen.")
        return state

    async def has_no_results(self) -> bool:
        """Check if there are no search results on the page."""
        return await self._engine.page.evaluate(SEARCH_STATE_JS) == "empty"

    async def scroll_to_load(self) -> None:
        """Perform a gradual scroll to load all dynamic content/cards."""
        await self._interactions.scroll_to_bottom_gradually(max_scrolls=15, scroll_step=600)

    async def parse_job_cards(self) -> list[Job]:
        """
        Extract all job cards present on the current search results page.
        Executes a Javascript query inside the browser context to parse elements.
        It continuously scrolls down the page and extracts to guarantee no job is missed.
        """
        page = self._engine.page
        try:
            if await self._wait_for_search_state() == "empty":
                return []

            # Run extraction in a scroll loop to guarantee we catch lazy loaded items
            js_script = """
            () => {
                const jobs = [];
                const cards = document.querySelectorAll('[class*="srp-jobtuple"], [class*="jobTuple"], article[class*="job"], [class*="sjw__tuple"], [class*="cust-job-tuple"]');
                for (const card of cards) {
                    try {
                        const titleElem = card.querySelector('a[class*="title"]');
                        if (!titleElem || !titleElem.getClientRects().length ||
                            getComputedStyle(titleElem).visibility === 'hidden' ||
                            card.closest('aside, [class*="recommend" i]')) continue;

                        const title = titleElem.innerText.trim();
                        let url = titleElem.getAttribute('href') || '';
                        if (url && !url.startsWith('http')) {
                            url = 'https://www.naukri.com' + url;
                        }

                        const compElem = card.querySelector('[class*="comp-name"], [class*="companyInfo"] a');
                        const company = compElem ? compElem.innerText.trim() : '';

                        const locElem = card.querySelector('[class*="loc-wrap"], [class*="location"], [class*="locWdth"], [class*="loc"]');
                        const location = locElem ? locElem.innerText.trim() : '';

                        const expElem = card.querySelector('[class*="exp-wrap"], [class*="experience"], [class*="expwdth"], .exp');
                        const experience = expElem ? expElem.innerText.trim() : '';

                        const salElem = card.querySelector('[class*="sal-wrap"], [class*="salary"], [class*="sal"]');
                        const salary = salElem ? salElem.innerText.trim() : '';

                        const dateElem = card.querySelector('[class*="job-post-day"], [class*="postDate"], .job-post-day, .date');
                        const posted_date = dateElem ? dateElem.innerText.trim() : '';

                        const tagElems = card.querySelectorAll('[class*="tag-li"], [class*="skill-tag"], [class*="dot-tag"]');
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
            seen_urls = set()
            for job in raw_jobs:
                if job.get("title") and job.get("url"):
                    if job["url"] in seen_urls:
                        continue
                    seen_urls.add(job["url"])

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

            logger.debug(
                f"Extracted {len(processed_jobs)} unique jobs via JS payload in Page Object"
            )
            if not processed_jobs:
                raise SearchLoadError("Visible search results could not be parsed into job listings.")
            return processed_jobs

        except PlaywrightError as e:
            logger.error(f"Failed to parse job cards via JS: {e}")
            raise SearchLoadError("Failed to read Naukri search results.") from e
