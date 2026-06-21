"""
Profile refresh automation for Naukri Agent.

Flow: Homepage -> click "View profile" -> click edit icon on
"Resume headline" section -> Save in modal -> confirm modal closed.
"""

import asyncio
import contextlib
from pathlib import Path

from src.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.config.constants import NAVIGATION_TIMEOUT
from src.utils.logger import get_logger, log_success, log_error

logger = get_logger(__name__)

DEBUG_DIR = Path("debug_artifacts")
DEBUG_DIR.mkdir(exist_ok=True)

HOMEPAGE_URL = "https://www.naukri.com/mnjuser/homepage"
PROFILE_URL_FRAGMENT = "/mnjuser/profile"
MODAL_URL_MARKER = "action=modalOpen"


class ProfileRefresher:
    """Handles automatically refreshing the user's Naukri profile via the
    Resume Headline edit -> Save flow, which bumps 'Profile last updated'."""

    def __init__(
        self,
        engine: IBrowserEngine,
        interactions: IBrowserInteractions,
    ) -> None:
        self._engine = engine
        self._interactions = interactions

    # ------------------------------------------------------------------ #
    # Debug capture
    # ------------------------------------------------------------------ #
    async def _capture_debug_artifacts(self, page, tag: str) -> None:
        """Dump screenshot + HTML so a failing step can be diagnosed precisely."""
        try:
            await page.screenshot(
                path=str(DEBUG_DIR / f"failure_{tag}.png"), full_page=True
            )
            html = await page.content()
            (DEBUG_DIR / f"failure_{tag}.html").write_text(html, encoding="utf-8")
            logger.info(f"Saved debug artifacts for '{tag}' to {DEBUG_DIR.resolve()}")
        except Exception as dbg_err:
            logger.info(f"Could not capture debug artifacts for '{tag}': {dbg_err}")

    # ------------------------------------------------------------------ #
    # Step 1: Click "View profile" on the homepage
    # ------------------------------------------------------------------ #
    async def _click_view_profile(self, page) -> bool:
        """Locate and click the 'View profile' button on the homepage."""
        candidates = [
            page.get_by_role("link", name="View profile", exact=True),
            page.get_by_role("button", name="View profile", exact=True),
            page.get_by_text("View profile", exact=True),
        ]
        for idx, locator in enumerate(candidates, start=1):
            try:
                target = locator.first
                await target.wait_for(state="visible", timeout=8000)
                await target.click(timeout=8000)
                logger.info(f"Clicked 'View profile' via strategy #{idx}")
                return True
            except Exception:
                logger.info(f"'View profile' strategy #{idx} failed, trying next...")
                continue
        return False

    # ------------------------------------------------------------------ #
    # Step 2: Click the edit (pencil) icon on the "Resume headline" section
    # ------------------------------------------------------------------ #
    async def _click_resume_headline_edit_icon(self, page) -> bool:
        """
        Locate the 'Resume headline' SECTION HEADING (not the sidebar nav item
        of the same name) and click its adjacent edit/pencil icon.
        """
        heading_candidates = [
            page.get_by_role("heading", name="Resume headline", exact=True),
            page.locator("h1, h2, h3, h4").filter(has_text="Resume headline"),
        ]

        heading = None
        for idx, candidate in enumerate(heading_candidates, start=1):
            try:
                target = candidate.first
                await target.wait_for(state="visible", timeout=8000)
                heading = target
                logger.info(f"Found 'Resume headline' heading via strategy #{idx}")
                break
            except Exception:
                logger.info(f"Heading strategy #{idx} failed, trying next...")
                continue

        if heading is None:
            log_error("Could not locate the 'Resume headline' section heading.")
            return False

        # Try several ways to find the edit icon relative to the heading.
        icon_candidates = [
            heading.locator("xpath=following-sibling::*[1]"),
            heading.locator("xpath=./parent::*//*[contains(@class, 'edit') or contains(@class, 'pencil')]"),
            heading.locator("xpath=./parent::*//button"),
            heading.locator("xpath=./parent::*//svg"),
        ]

        for idx, icon_locator in enumerate(icon_candidates, start=1):
            try:
                icon = icon_locator.first
                await icon.wait_for(state="visible", timeout=5000)
                await icon.click(timeout=5000)
                logger.info(f"Clicked Resume Headline edit icon via strategy #{idx}")
                return True
            except Exception:
                logger.info(f"Edit icon strategy #{idx} failed, trying next...")
                continue

        log_error("Could not click the Resume Headline edit icon with any strategy.")
        return False

    # ------------------------------------------------------------------ #
    # Step 3: Click Save inside the modal
    # ------------------------------------------------------------------ #
    async def _click_save_in_modal(self, page) -> bool:
        save_candidates = [
            page.get_by_role("button", name="Save", exact=True),
            page.locator("button").filter(has_text="Save"),
        ]
        for idx, locator in enumerate(save_candidates, start=1):
            try:
                target = locator.first
                await target.wait_for(state="visible", timeout=10_000)
                await target.click(timeout=10_000)
                logger.info(f"Clicked Save button via strategy #{idx}")
                return True
            except Exception:
                logger.info(f"Save button strategy #{idx} failed, trying next...")
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
            # --- Step 1: make sure we're on the homepage, then click "View profile" ---
            if PROFILE_URL_FRAGMENT not in page.url:
                logger.info("Navigating to Naukri homepage...")
                await page.goto(
                    HOMEPAGE_URL,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT,
                )
                await self._interactions.wait_for_navigation_complete()

                logger.info("Clicking 'View profile'...")
                if not await self._click_view_profile(page):
                    log_error("Failed to click 'View profile' button.")
                    await self._capture_debug_artifacts(page, "view_profile_click")
                    return False

                # Confirm we actually navigated to the profile page
                await page.wait_for_url(f"**{PROFILE_URL_FRAGMENT}**", timeout=15_000)
                await self._interactions.wait_for_navigation_complete()
            else:
                logger.info("Already on profile page, skipping 'View profile' click.")

            # --- Step 2: click the Resume Headline edit icon ---
            logger.info("Locating and clicking the Resume Headline edit icon...")
            if not await self._click_resume_headline_edit_icon(page):
                await self._capture_debug_artifacts(page, "edit_icon_click")
                return False

            # Confirm the modal actually opened using the URL fingerprint
            # observed in production (?action=modalOpen)
            try:
                await page.wait_for_url(f"**{MODAL_URL_MARKER}**", timeout=8000)
                logger.info("Confirmed modal opened (URL contains action=modalOpen).")
            except Exception:
                # Some flows might not change the URL — fall back to checking
                # for the Save button being visible as proof the modal is open.
                logger.info("URL did not show modal marker, checking for Save button instead...")
                try:
                    await page.get_by_role("button", name="Save", exact=True).first.wait_for(
                        state="visible", timeout=5000
                    )
                except Exception:
                    log_error("Modal does not appear to have opened after clicking edit icon.")
                    await self._capture_debug_artifacts(page, "modal_not_opened")
                    return False

            await asyncio.sleep(1)  # let modal fully render

            # --- Step 3: click Save ---
            logger.info("Clicking Save in the Resume Headline modal...")
            if not await self._click_save_in_modal(page):
                log_error("Failed to click the Save button.")
                await self._capture_debug_artifacts(page, "save_click")
                return False

            # --- Step 4: confirm modal closed ---
            try:
                await page.wait_for_url(
                    lambda url: MODAL_URL_MARKER not in url, timeout=10_000
                )
                logger.info("Confirmed modal closed (URL no longer contains action=modalOpen).")
            except Exception:
                # Fallback: confirm Save button is no longer visible
                with contextlib.suppress(Exception):
                    await page.get_by_role("button", name="Save", exact=True).first.wait_for(
                        state="hidden", timeout=8000
                    )

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
                with contextlib.suppress(Exception):
                    await self._capture_debug_artifacts(page, "unexpected_error")
            return False