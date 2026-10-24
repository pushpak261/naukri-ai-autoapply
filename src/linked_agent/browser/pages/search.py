"""
SearchPage Page Object for LinkedIn.
Encapsulates all search listing page actions and scraping evaluation scripts.

Uses JavaScript-based extraction that works with LinkedIn's current React SPA DOM,
rather than fragile CSS selectors.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode, urlunparse

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.linked_agent.browser.pages.base import BasePage
from src.linked_agent.config.constants import SearchSelectors
from src.linked_agent.models.entities import Job
from src.linked_agent.utils.helpers import clean_text, extract_linkedin_job_id
from src.linked_agent.utils.exceptions import LoginError, RateLimitError
from src.linked_agent.utils.logger import get_logger
import contextlib

logger = get_logger(__name__)


class LinkedInSearchPage(BasePage):
    """Page Object representing the LinkedIn Job Search Results page."""

    def _location_cache_path(self) -> Path | None:
        root = getattr(getattr(self._engine, "_settings", None), "project_root", None)
        return root / "data/linkedin/search_locations.json" if isinstance(root, Path) else None

    def _location_ids(self) -> dict[str, str]:
        if hasattr(self, "_resolved_location_ids"):
            return self._resolved_location_ids
        locations = {}
        path = self._location_cache_path()
        if path:
            try:
                saved = json.loads(path.read_text())
                if isinstance(saved, dict):
                    locations = {
                        name: identifier for name, identifier in saved.items()
                        if isinstance(name, str) and isinstance(identifier, str) and identifier.isdigit()
                    }
            except (OSError, ValueError):
                pass
        self._resolved_location_ids = locations
        return locations

    def _remember_location(self, requested: str, identifier: str) -> None:
        if not identifier.isdigit():
            return
        locations = self._location_ids()
        if locations.get(requested) == identifier:
            return
        locations[requested] = identifier
        path = self._location_cache_path()
        if path:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(f".{os.getpid()}.tmp")
                temporary.write_text(json.dumps(locations), encoding="utf-8")
                temporary.replace(path)
            except OSError as error:
                logger.warning("Cannot persist verified LinkedIn locations: %s", error)

    async def navigate_to_search(self, search_url: str) -> None:
        """Navigate to a specific LinkedIn job search URL with retries."""
        page = self._engine.page
        requested = parse_qs(urlparse(search_url).query).get("location", [""])[0]
        geo_ids = self._location_ids()
        if requested in geo_ids:
            parsed = urlparse(search_url)
            params = parse_qs(parsed.query)
            params["geoId"] = [geo_ids[requested]]
            search_url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Navigating to LinkedIn search (attempt {attempt}/{max_retries}): {search_url}"
                )
                response = await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                if response and response.status == 429:
                    raise RateLimitError("LinkedIn requested a pause (HTTP 429); stop and review before another run.")
                if response and response.status in (401, 403):
                    raise LoginError("LinkedIn requires sign-in or verification before searching.")
                with contextlib.suppress(PlaywrightTimeoutError):
                    await page.wait_for_load_state("networkidle", timeout=10000)

                # Detect silent redirects (LinkedIn often strips ?start= or sends to login)
                actual_url = page.url
                parsed_intended = urlparse(search_url)
                parsed_actual = urlparse(actual_url)

                intended_params = parse_qs(parsed_intended.query)
                actual_params = parse_qs(parsed_actual.query)

                intended_start = intended_params.get("start", [None])[0]
                actual_start = actual_params.get("start", [None])[0]

                if intended_start and intended_start != actual_start:
                    if actual_start is None:
                        logger.warning(
                            f"LinkedIN redirected paginated URL — 'start' parameter lost. "
                            f"Intended start={intended_start}, Actual URL has no start. "
                            f"Likely no more pages available."
                        )
                    else:
                        logger.warning(
                            f"LinkedIN redirected pagination — start={intended_start} -> start={actual_start}"
                        )

                # Check for blocking pages
                if "/login" in actual_url or "signup" in actual_url:
                    raise LoginError("Navigated to login/signup page — session expired")
                if "captcha" in actual_url.lower() or "challenge" in actual_url.lower():
                    raise LoginError("LinkedIn verification requires your attention")

                self._requested_search_params = intended_params
                await self._ensure_search_location(requested)
                if "2" in intended_params.get("f_WT", [""])[0].split(","):
                    await self._ensure_search_location("Remote")
                await asyncio.sleep(2)
                return
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                logger.warning(f"Navigation attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    raise
                await asyncio.sleep(3 * attempt)

    async def _ensure_search_location(self, requested: str) -> None:
        """Modern LinkedIn can discard location= and reuse the last city.

        Resolve a requested place through the visible location picker, then
        retain its platform-provided geoId for subsequent pages of this search.
        """
        if not requested:
            return
        page = self._engine.page
        label = page.locator('[aria-label^="Location "]:visible').first
        if not await label.count():
            return  # Legacy layout still supports location= directly.
        if requested.casefold() == "remote":
            remote = page.locator('input[aria-label="Filter by Remote"]:checked')
            if not await remote.count():
                # The native input is visually hidden; its associated label is
                # the public control. A second copy lives in a hidden drawer.
                await page.locator("label:visible").filter(has_text=re.compile(r"^Remote$")).first.click()
                await page.locator('input[aria-label="Filter by Remote"]:checked').first.wait_for(state="attached")
            return

        def normalized(text):
            return re.sub(r"\bbangalore\b", "bengaluru", text.casefold())

        target = normalized(requested)
        if target not in normalized(await label.inner_text()):
            await label.click(timeout=5000)
            editor = page.locator('[contenteditable="true"][aria-label="Location"]:visible, input[role="combobox"][aria-label*="Location" i]:visible').first
            try:
                await editor.fill(requested, timeout=5000)
            except PlaywrightTimeoutError:
                controls = await page.evaluate("""() => [...document.querySelectorAll('input, [contenteditable], [aria-label^="Location "]')]
                    .filter(el=>el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
                    .map(el=>({tag:el.tagName,role:el.getAttribute('role'),label:el.getAttribute('aria-label'),
                        placeholder:el.getAttribute('placeholder'),editable:el.getAttribute('contenteditable'),
                        id:el.id, parentTag:el.parentElement.tagName,parentRole:el.parentElement.getAttribute('role'),
                        parentClass:el.parentElement.className}))""")
                logger.warning("Visible LinkedIn location controls after opening picker: %s", controls)
                root = getattr(getattr(self._engine, "_settings", None), "project_root", None)
                if isinstance(root, Path):
                    diagnostic = root / "data/linkedin/location-picker.png"
                    diagnostic.parent.mkdir(parents=True, exist_ok=True)
                    with contextlib.suppress(PlaywrightError):
                        await page.screenshot(path=str(diagnostic))
                raise
            # Autocomplete can replace/close its popover before Playwright's
            # click actionability checks finish. Capture the actual suggested
            # search link while it is present, then follow that same link.
            suggestion = await page.wait_for_function(
                """target => {
                    const normalize = text => text.toLowerCase().replace(/\\bbangalore\\b/g, 'bengaluru');
                    const links = [...document.querySelectorAll('#semanticSearchBoxLocationList a[href]')];
                    const match = links.find(link => normalize(link.textContent.trim()).startsWith(target));
                    return match ? match.href : null;
                }""",
                arg=target,
                timeout=10000,
            )
            destination = await suggestion.json_value()
            parsed = urlparse(destination)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "www.linkedin.com"
                or not parsed.path.startswith("/jobs/search")
                or not parse_qs(parsed.query).get("geoId", [""])[0].isdigit()
            ):
                raise RuntimeError("LinkedIn returned an invalid location suggestion")
            params = parse_qs(parsed.query)
            intended = getattr(self, "_requested_search_params", {})
            for key in ("keywords", "f_TPR", "f_E", "f_WT", "f_AL", "f_JT", "sortBy", "start"):
                if key in intended:
                    params[key] = intended[key]
            if intended:
                destination = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
            await page.goto(destination, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_function(
                "target => {const el=[...document.querySelectorAll('[aria-label^=\"Location \"]')].find(el=>el.getClientRects().length); return el && el.textContent.toLowerCase().replace(/\\bbangalore\\b/g,'bengaluru').includes(target);}",
                arg=target,
                timeout=10000,
            )
        geo_id = parse_qs(urlparse(page.url).query).get("geoId", [""])[0]
        if geo_id:
            self._remember_location(requested, geo_id)

    async def has_no_results(self) -> bool:
        """Check if there are no search results or if the page shows an empty/error state."""
        page = self._engine.page
        try:
            # 1. Quick check using constants selector
            if await self._interactions.element_exists(SearchSelectors.NO_RESULTS):
                return True

            # 2. JS evaluation checking body text and specific empty state elements
            no_results = await page.evaluate("""
                () => {
                    const text = document.body ? document.body.innerText : '';
                    if (
                        text.includes('No matching jobs found') ||
                        text.includes('No matching jobs') ||
                        text.includes('No jobs found') ||
                        text.includes('No results found') ||
                        text.includes("Unfortunately, things aren't loading")
                    ) {
                        return true;
                    }
                    const noResultsEl = document.querySelector(
                        '.jobs-search-results__no-results, .jobs-search-no-results, ' +
                        '.jobs-search-two-pane__no-results, [class*="no-results"]'
                    );
                    if (noResultsEl && noResultsEl.offsetParent !== null) {
                        return true;
                    }
                    return false;
                }
            """)
            return bool(no_results)
        except Exception as e:
            logger.debug(f"has_no_results check encountered error: {e}")
            return False

    async def get_total_result_count(self) -> int | None:
        """
        Extract the total matching jobs count from the current search results page header.
        Returns the integer count (e.g. 12 for '12 results'), or None if not found.
        """
        page = self._engine.page
        try:
            count = await page.evaluate("""
                () => {
                    // Try specific search header elements
                    const selectors = [
                        '.jobs-search-results-list__header',
                        '.jobs-search-results-list__subtitle',
                        'small.jobs-search-results-list__text',
                        '.jobs-search-results-list__title',
                        'header.jobs-search-results-list__header',
                        'h1'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const txt = (el.innerText || '').trim();
                            const match = txt.match(/([\\d,]+)\\+?\\s+(results|jobs)/i);
                            if (match) {
                                const num = parseInt(match[1].replace(/,/g, ''), 10);
                                if (!isNaN(num)) return num;
                            }
                        }
                    }
                    // Try page text
                    const bodyText = document.body ? document.body.innerText : '';
                    const m = bodyText.match(/([\\d,]+)\\+?\\s+(results|jobs)\\s+found/i) || bodyText.match(/([\\d,]+)\\+?\\s+results/i);
                    if (m) {
                        const num = parseInt(m[1].replace(/,/g, ''), 10);
                        if (!isNaN(num)) return num;
                    }
                    return null;
                }
            """)
            return count
        except Exception as e:
            logger.debug(f"Failed to extract total result count: {e}")
            return None

    # ── Public methods ──────────────────────────────────────────────────────

    async def parse_job_cards(self, search_url: str = "") -> list[Job]:
        """
        Extract ALL job cards from the current search results page.

        Robust collection pipeline:
          1. Check for 'no results' state early to avoid timeouts.
          2. Wait for page + first card to render.
          3. Find the scrollable job-list container (overflow parent walk-up).
          4. Adaptive scroll-to-load with stabilization detection.
          5. Try JSON payload extraction from embedded page data.
          6. Fall back to comprehensive DOM extraction if no payload.
          7. Deduplicate by URL, build Job objects with LinkedIn IDs.
        """
        if await self.has_no_results():
            logger.info("Page indicates no search results — skipping card collection")
            return []

        page = self._engine.page
        await self._wait_for_search_page_ready(page)

        if await self.has_no_results():
            logger.info("Page indicates no search results after ready check — returning empty list")
            return []

        container_found = await self._find_scrollable_container(page)

        card_count = await self._adaptive_scroll_to_load_all(page, container_found)
        logger.info(f"Final card count after adaptive scroll: {card_count}")

        # Embedded payloads may describe only the selected sidebar job. Always
        # collect rendered result cards too, then deduplicate during conversion.
        jobs = await self._extract_cards_from_dom(page)
        jobs.extend(await self._try_json_payload_extraction(page))

        source_url = page.url if "/jobs/search-results" in page.url else search_url
        return self._build_job_objects(jobs, source_url)

    async def go_to_next_page(self) -> bool:
        """
        Navigate to the next page via click-based pagination.
        Returns True if a new page was loaded, False if at the last page.
        """
        if await self.has_no_results():
            return False

        page = self._engine.page
        for attempt in range(2):
            try:
                next_btn = await page.query_selector(
                    'button[data-testid="pagination-controls-next-button-visible"]:not([disabled]), '
                    'button[aria-label="View next page"]:not([disabled]):not(.artdeco-button--disabled), '
                    'button[aria-label*="next page" i]:not([disabled]):not(.artdeco-button--disabled), '
                    'li.artdeco-pagination__indicator--number:last-child button:not([disabled])'
                )
                if next_btn and await next_btn.is_visible():
                    # Check if aria-disabled is true
                    aria_disabled = await next_btn.get_attribute('aria-disabled')
                    if aria_disabled == 'true':
                        logger.info("Next page button is aria-disabled — at last page")
                        return False

                    await next_btn.click()
                    with contextlib.suppress(PlaywrightTimeoutError):
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    await asyncio.sleep(2)

                    if await self.has_no_results():
                        logger.info("Land on empty results after clicking Next — at end of pagination")
                        return False

                    return True
                return False
            except PlaywrightError as e:
                logger.debug(f"Next page navigation attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2)
        return False

    async def click_job_card(self, index: int) -> bool:
        """Click the job card at the given index to open the detail sidebar.

        Uses JS to scroll the card into view and click, which handles
        LinkedIn's virtualization where cards exist in DOM but are hidden.
        Falls back to Playwright locator click if JS click fails.
        """
        page = self._engine.page

        for attempt in range(3):
            try:
                cards = page.locator('a[href*="/jobs/view/"]')
                count = await cards.count()

                if index >= count:
                    logger.warning(f"Card index {index} out of range (have {count}) — scrolling to load more (attempt {attempt+1})")
                    for _ in range(6):
                        with contextlib.suppress(Exception):
                            await page.evaluate("""
                                () => {
                                    const card = document.querySelector('a[href*="/jobs/view/"]');
                                    if (!card) return false;
                                    let el = card.parentElement;
                                    while (el && el !== document.body && el !== document.documentElement) {
                                        const style = window.getComputedStyle(el);
                                        if (
                                            style.overflow === 'auto' || style.overflow === 'scroll'
                                            || style.overflowY === 'auto' || style.overflowY === 'scroll'
                                        ) {
                                            const prev = el.scrollTop;
                                            el.scrollTop += el.clientHeight || 500;
                                            el.dispatchEvent(new Event('scroll', {bubbles: true}));
                                            return (el.scrollTop - prev) > 0;
                                        }
                                        el = el.parentElement;
                                    }
                                    return false;
                                }
                            """)
                        await asyncio.sleep(1)
                    await asyncio.sleep(2)
                    continue

                try:
                    clicked = await page.evaluate(f"""
                        () => {{
                            const cards = document.querySelectorAll('a[href*="/jobs/view/"]');
                            const card = cards[{index}];
                            if (!card) return false;
                            card.scrollIntoView({{behavior: 'instant', block: 'center'}});
                            card.click();
                            return true;
                        }}
                    """)
                    if not clicked:
                        raise PlaywrightError("Card not found in DOM")
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.debug(f"JS click failed for card {index}: {e}, falling back to Playwright click")
                    await cards.nth(index).click(timeout=15000)
                    await asyncio.sleep(2)

                await asyncio.sleep(2)
                try:
                    await page.wait_for_selector(
                        'button[aria-label*="Apply" i], button[aria-label*="already applied" i]',
                        timeout=10000, state='visible'
                    )
                except PlaywrightTimeoutError:
                    logger.debug("Apply button area not yet visible after card click, continuing")
                return True
            except PlaywrightError as e:
                logger.warning(f"Failed to click job card {index}: {e}")

        logger.warning(f"Card index {index} could not be clicked after 3 attempts")
        return False

    async def extract_sidebar_details(self) -> dict:
        """Extract job details from the sidebar panel that opens after clicking a job card."""
        page = self._engine.page
        js_script = """() => {
            const details = {};
            const h1 = document.querySelector('h1');
            details.title = h1 ? h1.textContent.trim() : '';
            const comp = document.querySelector('.job-details-jobs-unified-top-card__company-name a, .job-details-jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__second-line a');
            details.company = comp ? comp.textContent.trim() : '';
            const loc = document.querySelector('.job-details-jobs-unified-top-card__primary-description span, .job-details-jobs-unified-top-card__bullet');
            details.location = loc ? loc.textContent.trim() : '';

            const descSelectors = ['[componentkey^="JobDetails_AboutTheJob_"]', '.jobs-description__content', '.jobs-box__html-content', '.description__text', '.show-more-less-html__markup', 'div.jobs-description', '.job-details-jobs-unified-top-card__job-insight'];
            let descText = '';
            for (const sel of descSelectors) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim().length > 20) {
                    descText = el.textContent.trim();
                    break;
                }
            }
            if (!descText) {
                let maxLen = 0;
                document.querySelectorAll('div, section').forEach(el => {
                    const t = el.textContent.trim();
                    if (t.length > maxLen && t.length < 50000 && t.length > 200) {
                        if (!t.includes('Jobs you may be interested in') && !t.includes('People also viewed') && !el.closest('.jobs-search-results-list')) {
                            maxLen = t.length;
                            descText = t;
                        }
                    }
                });
            }
            details.description = descText;
            const skillEls = document.querySelectorAll('.job-details-jobs-unified-top-card__job-insight span, .job-insight__text');
            details.skills = Array.from(skillEls).map(e => e.textContent.trim()).join(', ');

            let easyApply = false;
            const allBtns = document.querySelectorAll('button');
            for (const btn of allBtns) {
                const btnText = (btn.innerText || '').toLowerCase();
                const btnLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                if (btnText.includes('easy apply') || btnLabel.includes('easy apply')) {
                    easyApply = true;
                    break;
                }
            }
            details.easy_apply = easyApply;

            let alreadyApplied = false;
            document.querySelectorAll('button, span').forEach(el => {
                const txt = el.textContent.trim().toLowerCase();
                const label = (el.getAttribute('aria-label') || '').toLowerCase();
                if (txt.includes('already applied') || label.includes('already applied') || (txt === 'applied' && el.tagName === 'BUTTON')) {
                    alreadyApplied = true;
                }
            });
            details.already_applied = alreadyApplied;

            let hasExternal = false;
            document.querySelectorAll('button, a').forEach(el => {
                const txt = el.textContent.trim();
                const label = el.getAttribute('aria-label') || '';
                if ((txt.includes('Apply') && !txt.includes('Easy Apply') && !txt.includes('Show results') && !txt.includes('filter')) || label.includes('Apply on company')) {
                    hasExternal = true;
                }
            });
            details.external_apply = hasExternal;
            details.url = window.location.href;
            return details;
        }"""
        try:
            result = await page.evaluate(js_script)
            return result or {}
        except PlaywrightError as e:
            logger.error(f"Sidebar extraction failed: {e}")
            return {}

    async def close_sidebar(self) -> None:
        """Close the job detail sidebar by pressing Escape or clicking dismiss."""
        page = self._engine.page
        try:
            await page.keyboard.press('Escape')
            await asyncio.sleep(1)
        except PlaywrightError:
            pass

    # ── Private: page readiness ─────────────────────────────────────────────

    async def _wait_for_search_page_ready(self, page) -> None:
        """Wait for DOM, network idle, and at least one job card to render."""
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("domcontentloaded", timeout=10_000)
        await asyncio.sleep(1)

        if await self.has_no_results():
            return

        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=5_000)

        if await self.has_no_results():
            return

        with contextlib.suppress(Exception):
            await page.wait_for_selector(
                '[componentkey^="job-card-component-ref-"][role="button"], [data-view-name="job-card"], a[href*="/jobs/view/"]',
                timeout=10_000,
            )
        await asyncio.sleep(1)

    # ── Private: container detection ────────────────────────────────────────

    async def _find_scrollable_container(self, page) -> bool:
        """
        Find the scrollable container holding job cards.
        Walks up from the first card to find the overflow:auto ancestor.
        Uses a unique property on window (__li_jobContainer) to avoid collisions.
        """
        try:
            found = await page.evaluate("""
                () => {
                    const card = document.querySelector(
                        '[componentkey^="job-card-component-ref-"][role="button"], '
                        + '[data-view-name="job-card"], li[data-view-name="job-card"], '
                        + 'a[href*="/jobs/view/"]'
                    );
                    if (!card) return false;

                    let el = card.parentElement;
                    while (el && el !== document.body && el !== document.documentElement) {
                        const style = window.getComputedStyle(el);
                        if (
                            style.overflow === 'auto' || style.overflow === 'scroll'
                            || style.overflowY === 'auto' || style.overflowY === 'scroll'
                            || style.overflowX === 'auto' || style.overflowX === 'scroll'
                            || style.overflowY === 'overlay'
                        ) {
                            window.__li_jobContainer = el;
                            return true;
                        }
                        el = el.parentElement;
                    }
                    return false;
                }
            """)
            if found:
                return True
        except Exception:
            pass

        logger.warning("Could not find scrollable job container — trying fallback selectors")
        try:
            found = await page.evaluate("""
                () => {
                    const c = document.querySelector('.jobs-search-results-list')
                        || document.querySelector('[class*="jobs-search__results-list"]')
                        || document.querySelector('[class*="scaffold-layout__list"]')
                        || document.querySelector('main[class*="scaffold"]');
                    if (c) {
                        window.__li_jobContainer = c;
                        return true;
                    }
                    return false;
                }
            """)
            return bool(found)
        except Exception:
            return False

    # ── Private: adaptive lazy loading scrolling ────────────────────────────

    async def _adaptive_scroll_to_load_all(self, page, container_found: bool) -> int:
        """
        Scroll the job-list container gradually until card count stabilizes.

        Instead of fixed 18 rounds, this adaptively scrolls and measures:
          - Each scroll step is ~1 viewport height
          - After each step, wait 400ms for lazy loading
          - Count cards; if count increased, reset stabilization counter
          - Stop when: 3 consecutive stable counts, OR 30s elapsed, OR 25+ cards
        """
        prev_count = 0
        stable_rounds = 0
        max_stable = 3
        max_time = 30.0
        start_time = asyncio.get_event_loop().time()
        mouse_wheel_used = False
        keyboard_used = False

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_time:
                logger.info(f"Adaptive scroll timed out after {max_time}s")
                break

            try:
                if container_found:
                    await page.evaluate("""
                        async () => {
                            const delay = ms => new Promise(r => setTimeout(r, ms));
                            const c = window.__li_jobContainer;
                            if (!c) return;
                            c.style.overflow = 'auto';
                            const viewH = c.clientHeight || 500;
                            const step = Math.max(250, viewH * 0.6);
                            const maxScroll = c.scrollHeight;
                            for (let pos = 0; pos < maxScroll; pos += step) {
                                c.scrollTop = pos;
                                await delay(200);
                            }
                            c.scrollTop = maxScroll;
                            await delay(200);
                        }
                    """)
                else:
                    await page.evaluate("""
                        () => window.scrollTo(0, document.body.scrollHeight || document.documentElement.scrollHeight);
                    """)

                await asyncio.sleep(0.4)

                if stable_rounds >= 1 and not mouse_wheel_used:
                    try:
                        if container_found:
                            first = page.locator('[data-view-name="job-card"]').first
                            if await first.count() > 0:
                                await first.hover()
                        await page.mouse.wheel(0, 2000)
                        mouse_wheel_used = True
                    except Exception:
                        pass

                if stable_rounds >= 2 and not keyboard_used:
                    try:
                        await page.keyboard.press('PageDown')
                        await asyncio.sleep(0.3)
                        await page.keyboard.press('End')
                        keyboard_used = True
                    except Exception:
                        pass

                count = await self._safe_card_count(page)
            except Exception as e:
                logger.debug(f"Adaptive scroll step failed: {e}")
                await asyncio.sleep(2)
                count = 0

            if count != prev_count:
                logger.info(f"Scroll step: {count} cards (stable rounds reset)")
                stable_rounds = 0
            else:
                stable_rounds += 1

            prev_count = count

            if count >= 25:
                logger.info("All 25 cards loaded")
                break

            if stable_rounds >= max_stable and count > 0:
                logger.info(f"Card count stable at {count} for {max_stable} rounds — stopping scroll")
                break

            await asyncio.sleep(0.5)

        return prev_count

    async def _safe_card_count(self, page) -> int:
        """Count job cards safely, returning 0 on error."""
        try:
            return await page.evaluate("""
                () => {
                    const modern = Array.from(document.querySelectorAll('[componentkey^="job-card-component-ref-"][role="button"]'))
                        .filter(card => card.getClientRects().length).length;
                    return modern || Math.max(
                        document.querySelectorAll('[data-view-name="job-card"], li[data-view-name="job-card"]').length,
                        document.querySelectorAll('a[href*="/jobs/view/"]').length
                    );
                }
            """)
        except Exception:
            return 0

    # ── Private: JSON payload extraction ────────────────────────────────────

    async def _try_json_payload_extraction(self, page) -> list[dict]:
        """
        Attempt to extract job data from LinkedIn's embedded JSON payloads.
        Checks multiple script tag patterns for structured job data.
        Returns a list of raw job dicts (same shape as DOM extraction returns),
        or an empty list if no payload was found.
        """
        js = """
        () => {
            const jobs = [];
            const seen = new Set();

            // ── Pattern 1: data-entity-urn on job cards ──────────────
            // Each <li data-view-name="job-card"> has data-entity-urn="urn:li:jobPosting:12345"
            try {
                const cardsWithUrn = document.querySelectorAll(
                    'li[data-view-name="job-card"][data-entity-urn*="jobPosting"]'
                );
                for (const card of cardsWithUrn) {
                    const urn = card.getAttribute('data-entity-urn') || '';
                    const jobId = urn.split(':').pop();
                    if (!jobId || seen.has(jobId)) continue;
                    seen.add(jobId);

                    const titleLink = card.querySelector('a[href*="/jobs/view/"]');
                    if (!titleLink) continue;
                    const title = (titleLink.textContent || '').trim();
                    let url = titleLink.getAttribute('href') || '';
                    if (!url || !title) continue;
                    if (!url.startsWith('http')) url = 'https://www.linkedin.com' + url;
                    url = url.split('?')[0];

                    const subtitles = card.querySelectorAll(
                        '.artdeco-entity-lockup__subtitle, [class*="entity-lockup__subtitle"], [class*="card__company"], [class*="subtitle"]'
                    );
                    const company = subtitles.length > 0 ? subtitles[0].textContent.trim() : '';

                    const captions = card.querySelectorAll(
                        '.artdeco-entity-lockup__caption, [class*="entity-lockup__caption"], [class*="card__location"], [class*="caption"]'
                    );
                    const location = captions.length > 0 ? captions[0].textContent.trim() : '';

                    const timeEl = card.querySelector('time');
                    const posted = timeEl ? timeEl.textContent.trim() : '';

                    const easyApply = !!(
                        card.querySelector('button[aria-label*="Easy Apply"]')
                        || card.querySelector('[class*="easy-apply"]')
                        || (card.innerText || '').includes('Easy Apply')
                    );

                    const appText = (card.innerText || '').match(/(\\d+)\\s*applicant/i);
                    const applicantCount = appText ? parseInt(appText[1]) : 0;

                    jobs.push({
                        title, company, location, url,
                        linkedin_job_id: jobId,
                        posted_date: posted, easy_apply: easyApply,
                        applicant_count: applicantCount, description: '',
                        card_index: jobs.length
                    });
                }
            } catch (e) {}

            return jobs;
        }
        """
        try:
            result = await page.evaluate(js)
            if result and len(result) > 0:
                logger.info(f"Extracted {len(result)} jobs via JSON payload (entity-urn)")
                return result
        except Exception:
            pass

        return []

    # ── Private: DOM-based extraction (fallback) ────────────────────────────

    async def _extract_cards_from_dom(self, page) -> list[dict]:
        """
        Comprehensive DOM-based job card extraction.
        Merges the old 3-strategy approach into one robust script that
        tries every possible selector for every card on the page.
        """
        js = r"""
        () => {
            const jobs = [];
            const seen = new Set();
            let cardIdx = 0;

            // New LinkedIn search-results pages use clickable components with
            // stable job IDs instead of /jobs/view anchors and legacy CSS.
            for (const card of document.querySelectorAll('[componentkey^="job-card-component-ref-"][role="button"]')) {
                if (!card.getClientRects().length) continue;
                const key = card.getAttribute('componentkey') || '';
                const id = key.match(/^job-card-component-ref-(\d+)$/)?.[1];
                if (!id) continue;
                const dismiss = card.querySelector('button[aria-label^="Dismiss "]');
                const paragraphs = Array.from(card.querySelectorAll('p'));
                const title = dismiss
                    ? (dismiss.getAttribute('aria-label') || '').replace(/^Dismiss /, '').replace(/ job$/, '')
                    : (paragraphs[0]?.querySelector('[aria-hidden="true"]')?.textContent || paragraphs[0]?.textContent || '').replace(/\s*\(Verified job\)/g, '').trim();
                if (!title) continue;
                const url = 'https://www.linkedin.com/jobs/view/' + id;
                if (seen.has(url)) continue;
                seen.add(url);
                const text = card.innerText || '';
                const posted = paragraphs.map(p => p.innerText.trim()).find(t => /(?:\d+\s+(?:minute|hour|day|week)|just now|today)/i.test(t)) || '';
                jobs.push({title, company: paragraphs[1]?.innerText.trim() || '',
                    location: paragraphs[2]?.innerText.trim() || '', url,
                    posted_date: posted, easy_apply: /easy apply/i.test(text),
                    applicant_count: 0, description: '', card_index: cardIdx++,
                    linkedin_job_id: id});
            }

            // A modern result list is complete. Legacy anchors elsewhere belong
            // to the selected job or recommendations, not additional results.
            if (jobs.length) return jobs;

            // Collect all candidate card nodes (any element that might be a job card)
            const candidates = [];
            const allCards = document.querySelectorAll(
                '[data-view-name="job-card"], li[data-view-name="job-card"], '
                + '.jobs-search-results__list-item, .job-card-container, '
                + 'li.jobs-search-results__list-item, div[data-entity-urn*="jobPosting"], '
                + 'a[href*="/jobs/view/"]'
            );
            for (const el of allCards) {
                const href = el.tagName === 'A' ? el.getAttribute('href') : (el.querySelector('a[href*="/jobs/view/"]')?.getAttribute('href') || '');
                if (href && !seen.has(href.split('?')[0])) {
                    candidates.push(el);
                }
            }

            for (const card of candidates) {
                try {
                    // Title & URL
                    const titleLink = card.tagName === 'A'
                        ? card
                        : (card.querySelector('a[href*="/jobs/view/"]')
                            || card.querySelector('a[href*="/jobs/search/"]')
                            || card.querySelector('.job-card-list__title--link, h3.base-card__full-link, h3 a, .job-card-container__link, span.artdeco-entity-lockup__title a'));
                    if (!titleLink) continue;

                    const title = (titleLink.textContent || '').trim();
                    let url = titleLink.getAttribute('href') || '';
                    if (!url || !title) continue;
                    if (!url.startsWith('http')) url = 'https://www.linkedin.com' + url;
                    url = url.split('?')[0];

                    if (seen.has(url)) continue;
                    seen.add(url);

                    // Entity URN job ID (most reliable)
                    let linkedin_job_id = '';
                    const li = card.closest('[data-entity-urn*="jobPosting"]');
                    if (li) {
                        const urn = li.getAttribute('data-entity-urn') || '';
                        linkedin_job_id = urn.split(':').pop() || '';
                    }

                    // Company
                    const company = (
                        card.querySelector('.artdeco-entity-lockup__subtitle, [class*="entity-lockup__subtitle"], [class*="card__company"], [class*="subtitle"], .job-card-container__primary-description, .job-card-container__company-name, .base-search-card__subtitle')
                        ?.textContent?.trim() || ''
                    );

                    // Location
                    const location = (
                        card.querySelector('.artdeco-entity-lockup__caption, [class*="entity-lockup__caption"], [class*="card__location"], [class*="caption"], .job-card-container__metadata-item, .job-card-container__bullet, .base-search-card__metadata span:first-child')
                        ?.textContent?.trim() || ''
                    );

                    // Posted time
                    const timeEl = card.querySelector('time');
                    const posted_date = timeEl ? timeEl.textContent.trim() : (
                        card.querySelector('.job-card-container__listed-date, .job-card-container__footer-item')
                        ?.textContent?.trim() || ''
                    );

                    // Easy Apply
                    const easy_apply = !!(
                        card.querySelector('button[aria-label*="Easy Apply"]')
                        || card.querySelector('[class*="easy-apply"]')
                        || (card.innerText || '').includes('Easy Apply')
                    );

                    // Applicant count
                    const appText = (card.innerText || '').match(/(\d+)\s*applicant/i);
                    const applicant_count = appText ? parseInt(appText[1]) : 0;

                    jobs.push({
                        title, company, location, url, posted_date,
                        easy_apply, applicant_count, description: '',
                        card_index: cardIdx++,
                        linkedin_job_id
                    });
                } catch (e) {}
            }

            return jobs;
        }
        """
        try:
            result = await page.evaluate(js)
            if not result:
                await self._diagnose_empty_results(page)
                return []
            logger.info(f"Extracted {len(result)} unique LinkedIn jobs via DOM extraction")
            return result
        except PlaywrightError as e:
            logger.error(f"DOM extraction failed: {e}")
            return []

    # ── Private: job object construction ────────────────────────────────────

    def _build_job_objects(self, raw_jobs: list[dict], search_url: str) -> list[Job]:
        """Convert raw job dicts to domain Job entities with dedup."""
        if not raw_jobs:
            return []

        processed: list[Job] = []
        seen_urls: set[str] = set()

        for job in raw_jobs:
            title = job.get("title", "")
            url = job.get("url", "")
            if not title or not url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            linkedin_job_id = job.get("linkedin_job_id", "") or extract_linkedin_job_id(url)

            processed.append(
                Job(
                    linkedin_job_id=linkedin_job_id,
                    title=clean_text(title),
                    company=clean_text(job.get("company", "")),
                    url=url,
                    location=clean_text(job.get("location", "")),
                    description="",
                    posted_date=clean_text(job.get("posted_date", "")),
                    easy_apply=job.get("easy_apply", False),
                    applicant_count=job.get("applicant_count", 0),
                    card_index=job.get("card_index", -1),
                    search_url=search_url,
                )
            )

        logger.info(f"Built {len(processed)} Job objects from extracted cards")
        return processed

    # ── Private: diagnostics ────────────────────────────────────────────────

    async def _diagnose_empty_results(self, page) -> None:
        """Log diagnostic info when no job cards are found."""
        try:
            url = page.url
            title = await page.title()
            logger.warning(f"DIAGNOSTIC: No jobs found. Page URL: {url}, Title: {title}")

            body_text = await page.evaluate("document.body?.innerText?.substring(0, 2000) || ''")
            if "sign in" in body_text.lower():
                logger.warning("DIAGNOSTIC: Page shows 'sign in' — login may have expired")
            if "captcha" in body_text.lower() or "verify" in body_text.lower():
                logger.warning("DIAGNOSTIC: CAPTCHA/verification challenge detected")
            if "no results" in body_text.lower() or "0 results" in body_text.lower():
                logger.warning("DIAGNOSTIC: LinkedIn says no results for this search")

            link_count = await page.evaluate("document.querySelectorAll('a').length")
            logger.warning(f"DIAGNOSTIC: Total links on page: {link_count}")

            job_links = await page.evaluate(
                "document.querySelectorAll('a[href*=\"/jobs/\"]').length"
            )
            logger.warning(f"DIAGNOSTIC: Links containing '/jobs/': {job_links}")

            logger.warning(f"DIAGNOSTIC: Page body preview: {body_text[:500]}")

        except Exception as e:
            logger.debug(f"Diagnostic failed: {e}")
