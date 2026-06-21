"""
Profile refresh automation for Naukri Agent.
"""

import asyncio
import contextlib
from pathlib import Path

from src.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.config.constants import ProfileSelectors, NAVIGATION_TIMEOUT
from src.utils.logger import get_logger, log_success, log_error

logger = get_logger(__name__)

DEBUG_DIR = Path("debug_artifacts")
DEBUG_DIR.mkdir(exist_ok=True)

# Fallback chain for the "Resume headline" edit icon.
# Ordered from most-specific/likely to most-generic, since Naukri's markup
# for this element has changed multiple times historically.
RESUME_HEADLINE_EDIT_FALLBACKS = [
    # 1. Original selector (kept first in case it starts working again,
    #    e.g. after an A/B test rollback)
    "//span[contains(text(), 'Resume headline')]/following-sibling::span[contains(@class, 'edit')]",
    # 2. Sibling could be an <a> or <i> icon tag instead of <span>
    "//span[contains(text(), 'Resume headline')]/following-sibling::*[contains(@class, 'edit')]",
    # 3. Edit icon might live in the same parent container, not as a direct sibling
    "//*[contains(text(), 'Resume headline')]/ancestor::div[1]//*[contains(@class, 'edit')]",
    # 4. Aria-label based (common on Naukri for icon-only buttons)
    "[aria-label*='Edit' i][aria-label*='headline' i]",
    # 5. Section-level data attribute, edit icon inside it
    "section[id*='resumeHeadline' i] [class*='edit' i]",
    "div[class*='resumeHeadline' i] [class*='edit' i]",
]


class ProfileRefresher:
    """Handles automatically refreshing the user's Naukri profile."""

    def __init__(
        self,
        engine: IBrowserEngine,
        interactions: IBrowserInteractions,
    ) -> None:
        self._engine = engine
        self._interactions = interactions

    async def _dismiss_known_overlays(self, page) -> None:
        """Best-effort dismissal of nudge modals that can block the headline section."""
        overlay_close_selectors = [
            "button[aria-label='Close']",
            "span.crossIcon",
            "div[class*='modal'] [class*='close' i]",
            "div[class*='overlay'] [class*='close' i]",
        ]
        for sel in overlay_close_selectors:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=1500):
                    await locator.click(timeout=1500)
                    logger.info(f"Dismissed overlay using selector: {sel}")
                    await asyncio.sleep(0.5)
            except Exception:
                continue  # overlay not present, that's fine

    async def _locate_edit_icon(self, page, timeout_per_attempt: int = 6000):
        """
        Try each fallback selector in turn. Returns the first locator that
        becomes attached, or None if all fail.
        """
        for idx, selector in enumerate(RESUME_HEADLINE_EDIT_FALLBACKS, start=1):
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="attached", timeout=timeout_per_attempt)
                logger.info(f"Edit icon located via fallback #{idx}: {selector}")
                return locator
            except Exception:
                logger.info(f"Fallback #{idx} did not match, trying next...")
                continue
        return None

    async def _capture_debug_artifacts(self, page) -> None:
        """Dump screenshot + relevant HTML so the failing selector can be fixed precisely."""
        try:
            await page.screenshot(path=str(DEBUG_DIR / "profile_page_failure.png"), full_page=True)
            html = await page.content()
            (DEBUG_DIR / "profile_page_failure.html").write_text(html, encoding="utf-8")
            logger.info(f"Saved debug screenshot and HTML to {DEBUG_DIR.resolve()}")
        except Exception as dbg_err:
            logger.info(f"Could not capture debug artifacts: {dbg_err}")

    async def refresh(self) -> bool:
        """
        Navigate to the profile, open the resume headline edit modal, and save it.
        This updates the 'Profile last updated' timestamp, keeping the profile active.
        """
        page = self._engine.page
        if not page:
            log_error("Browser page not available.")
            return False

        try:
            logger.info("Navigating to profile page...")
            await page.goto(
                ProfileSelectors.PROFILE_URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT,
            )
            await self._interactions.wait_for_navigation_complete()

            # Give any nudge modals a chance to render, then close them
            await asyncio.sleep(1.5)
            await self._dismiss_known_overlays(page)

            logger.info("Waiting for Resume Headline edit icon...")
            edit_icon = await self._locate_edit_icon(page)

            if edit_icon is None:
                log_error(
                    "Could not locate the Resume Headline edit icon with any known selector. "
                    "Naukri's profile page markup has likely changed."
                )
                await self._capture_debug_artifacts(page)
                return False

            await asyncio.sleep(2)  # let overlay/rendering settle

            logger.info("Clicking Resume Headline edit icon...")
            try:
                await edit_icon.click(timeout=10_000)
                clicked = True
            except Exception:
                clicked = False

            if not clicked:
                log_error("Failed to click the resume headline edit icon.")
                await self._capture_debug_artifacts(page)
                return False

            logger.info("Waiting for Save button in modal...")
            save_button = page.locator(ProfileSelectors.SAVE_BUTTON).first
            await save_button.wait_for(state="visible", timeout=10_000)

            await asyncio.sleep(1.5)  # mimic human pacing

            logger.info("Clicking Save button...")
            saved = await self._interactions.safe_click(
                ProfileSelectors.SAVE_BUTTON, timeout=10_000
            )

            if not saved:
                log_error("Failed to click the save button.")
                await self._capture_debug_artifacts(page)
                return False

            await asyncio.sleep(3)

            log_success("Profile successfully refreshed!")
            return True

        except Exception as e:
            error_msg = str(e)
            if "Target page, context or browser has been closed" in error_msg:
                log_error("Browser was closed by the user. Aborting profile refresh.")
            else:
                log_error(f"Error during profile refresh: {e}")
                logger.exception("Profile refresh failure details:")
                with contextlib.suppress(Exception):
                    await self._capture_debug_artifacts(page)
            return False
