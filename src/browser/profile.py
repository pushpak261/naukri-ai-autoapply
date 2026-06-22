"""
Profile refresh automation for Naukri Agent.

Flow:
    1. Click "View profile" on the homepage.
    2. If a feedback/nudge pop-up appears, close it.
    3. Click the edit (pencil) icon on the "Resume headline" section.
    4. Click Save inside the modal.

This module intentionally does nothing else — no debug-artifact dumping,
no unrelated helpers. Every step has bounded waits and a couple of
fallback selector strategies so a minor DOM/markup change on Naukri's
side doesn't immediately break the flow.
"""

import asyncio
import contextlib

from src.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.config.constants import NAVIGATION_TIMEOUT
from src.utils.logger import get_logger, log_success, log_error

logger = get_logger(__name__)

HOMEPAGE_URL = "https://www.naukri.com/mnjuser/homepage"
PROFILE_URL_FRAGMENT = "/mnjuser/profile"
MODAL_URL_MARKER = "action=modalOpen"

# Close ("X") icon selectors for the feedback / NPS pop-up that can appear
# right after the profile page loads (see "How likely are you to
# recommend our Power Profile service?").
POPUP_CLOSE_SELECTORS = [
    "button[aria-label='Close' i]",
    "[aria-label='close' i]",
    "div[class*='modal' i] svg",          # the X icon is often a bare svg
    "div[class*='modal' i] [class*='close' i]",
    "div[class*='overlay' i] [class*='close' i]",
    "[class*='cross' i]",
]

STEP_TIMEOUT_MS = 10_000
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.5


class ProfileRefresher:
    """Runs the View Profile -> dismiss popup -> edit headline -> Save flow."""

    def __init__(self, engine: IBrowserEngine, interactions: IBrowserInteractions) -> None:
        self._engine = engine
        self._interactions = interactions

    # ------------------------------------------------------------------ #
    # Step 1: Click "View profile"
    # ------------------------------------------------------------------ #
    async def _click_view_profile(self, page) -> bool:
        candidates = [
            page.get_by_role("link", name="View profile", exact=True),
            page.get_by_role("button", name="View profile", exact=True),
            page.get_by_text("View profile", exact=True),
        ]
        for idx, locator in enumerate(candidates, start=1):
            try:
                target = locator.first
                await target.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
                await target.click(timeout=STEP_TIMEOUT_MS)
                logger.info(f"Clicked 'View profile' (strategy #{idx}).")
                return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------ #
    # Step 2: Dismiss the feedback pop-up, if present
    # ------------------------------------------------------------------ #
    async def _dismiss_popup_if_present(self, page) -> bool:
        """Best-effort, non-fatal check for the feedback pop-up's X button."""
        for sel in POPUP_CLOSE_SELECTORS:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=1000):
                    await locator.click(timeout=2000)
                    logger.info(f"Closed feedback pop-up via selector: {sel}")
                    await asyncio.sleep(0.4)
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------ #
    # Step 3: Click the edit (pencil) icon on "Resume headline"
    # ------------------------------------------------------------------ #
    async def _modal_is_open(self, page) -> bool:
        """Verify the headline modal actually opened (URL marker or Save button)."""
        if MODAL_URL_MARKER in page.url:
            return True
        with contextlib.suppress(Exception):
            await page.get_by_role("button", name="Save", exact=True).first.wait_for(
                state="visible", timeout=2500
            )
            return True
        return False

    async def _click_resume_headline_edit_icon(self, page) -> bool:
        """
        The page contains TWO "Resume headline" text nodes: one in the
        left "Quick links" sidebar (plain text/link, no icon) and one as
        the section header in the main panel (with an adjacent pencil
        icon). We don't rely on a semantic <heading> role since the
        section label is just styled text, not an h1-h4. Instead we:
          1. Collect every element with that exact text.
          2. For each, try several ways to find a nearby clickable icon.
          3. Click it, then VERIFY the modal actually opened before
             declaring success — if not, keep trying the next candidate
             instead of silently returning a false positive.
        """
        text_matches = page.get_by_text("Resume headline", exact=True)

        try:
            await text_matches.first.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
        except Exception:
            log_error("Could not find any 'Resume headline' text on the page.")
            return False

        match_count = await text_matches.count()
        if match_count == 0:
            log_error("Could not find any 'Resume headline' text on the page.")
            return False

        # Generic "this looks like a clickable edit icon" predicate, reused
        # at every ancestor level below. Covers <svg>, <button>, and the
        # common icon-font pattern of a <span>/<i> carrying an edit/pencil
        # class (Naukri renders the pencil as exactly this kind of icon
        # tag sitting right next to the bold "Resume headline" label).
        ICON_XPATH = (
            ".//*[self::svg or self::button"
            " or contains(@class, 'edit') or contains(@class, 'pencil')"
            " or contains(@class, 'ic-edit')]"
        )

        for i in range(match_count):
            element = text_matches.nth(i)

            try:
                if not await element.is_visible(timeout=1500):
                    continue
            except Exception:
                continue

            # get_by_text(exact=True) matches the innermost element that
            # wraps the exact text — which may be nested a level or two
            # below the row that actually holds the icon (e.g. a <span>
            # inside an <h2> inside the flex row with the pencil). A fixed
            # "following-sibling" guess breaks the moment that nesting
            # changes, so instead we climb ancestor-by-ancestor and look
            # for an icon-like descendant at each level, stopping at the
            # first (closest/most specific) level where one is found.
            icon_locators = []
            for level in range(1, 6):
                ancestor = element.locator(f"xpath=ancestor::*[{level}]")
                icon_locators.append(ancestor.locator(f"xpath={ICON_XPATH}").first)
            # Plain sibling check too, in case the icon truly is a
            # same-level sibling on some other render of this page.
            icon_locators.append(element.locator("xpath=following-sibling::*[1]"))

            for icon_locator in icon_locators:
                try:
                    icon = icon_locator
                    await icon.wait_for(state="visible", timeout=1500)
                    await icon.click(timeout=3000)
                except Exception:
                    continue

                # Don't trust the click blindly — confirm the modal opened.
                if await self._modal_is_open(page):
                    logger.info(f"Clicked Resume Headline edit icon (text match #{i + 1}).")
                    return True

                # Click landed but nothing opened (wrong element, e.g. the
                # sidebar link, or an icon belonging to a different
                # section that got picked up at a too-high ancestor
                # level). Undo any accidental navigation and try the
                # next candidate.
                with contextlib.suppress(Exception):
                    if MODAL_URL_MARKER not in page.url and PROFILE_URL_FRAGMENT not in page.url:
                        await page.go_back(timeout=5000)

        log_error("Could not open the Resume Headline edit modal via any text match/icon combination.")
        return False

    # ------------------------------------------------------------------ #
    # Step 4: Click Save inside the modal
    # ------------------------------------------------------------------ #
    async def _click_save_in_modal(self, page) -> bool:
        save_candidates = [
            page.get_by_role("button", name="Save", exact=True),
            page.locator("button").filter(has_text="Save"),
        ]
        for locator in save_candidates:
            try:
                target = locator.first
                await target.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
                await target.click(timeout=STEP_TIMEOUT_MS)
                logger.info("Clicked Save in Resume Headline modal.")
                return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------ #
    # Main flow
    # ------------------------------------------------------------------ #
    async def refresh(self) -> bool:
        page = self._engine.page
        if not page:
            log_error("Browser page not available.")
            return False

        try:
            # --- Navigate to homepage if needed ---
            if PROFILE_URL_FRAGMENT not in page.url:
                logger.info("Navigating to Naukri homepage...")
                await page.goto(HOMEPAGE_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
                await self._interactions.wait_for_navigation_complete()

            # --- Step 1: Click View profile, with retries ---
            clicked = False
            for attempt in range(1, RETRY_ATTEMPTS + 1):
                if await self._click_view_profile(page):
                    clicked = True
                    break
                logger.info(f"'View profile' click attempt {attempt} failed, retrying...")
                await asyncio.sleep(RETRY_DELAY_SECONDS)

            if not clicked:
                log_error("Failed to click 'View profile' after retries.")
                return False

            await page.wait_for_url(f"**{PROFILE_URL_FRAGMENT}**", timeout=15_000)
            await self._interactions.wait_for_navigation_complete()

            # --- Step 2: Dismiss feedback pop-up if it shows up ---
            await asyncio.sleep(1.5)  # give the pop-up time to render
            await self._dismiss_popup_if_present(page)

            # --- Step 3: Click the Resume Headline edit icon, with retry ---
            opened = await self._click_resume_headline_edit_icon(page)
            if not opened:
                # A pop-up may have appeared right as we clicked and blocked it.
                await self._dismiss_popup_if_present(page)
                opened = await self._click_resume_headline_edit_icon(page)

            if not opened:
                log_error("Could not open the Resume Headline edit modal.")
                return False

            await asyncio.sleep(1)  # let modal fully render

            # --- Step 4: Click Save, with retry ---
            saved = await self._click_save_in_modal(page)
            if not saved:
                await self._dismiss_popup_if_present(page)
                saved = await self._click_save_in_modal(page)

            if not saved:
                log_error("Failed to click the Save button.")
                return False

            # Confirm the modal closed / save registered.
            with contextlib.suppress(Exception):
                await page.wait_for_url(lambda url: MODAL_URL_MARKER not in url, timeout=10_000)
            await asyncio.sleep(2)  # allow backend save to register

            log_success("Profile successfully refreshed!")
            return True

        except Exception as e:
            error_msg = str(e)
            if "Target page, context or browser has been closed" in error_msg:
                log_error("Browser was closed by the user. Aborting profile refresh.")
            else:
                log_error(f"Error during profile refresh: {e}")
                logger.exception("Profile refresh failure details:")
            return False