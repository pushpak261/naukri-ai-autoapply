"""
Profile refresh automation for Naukri Agent.
"""

import asyncio
from src.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.config.constants import ProfileSelectors, NAVIGATION_TIMEOUT
from src.utils.logger import get_logger, log_success, log_error

logger = get_logger(__name__)


class ProfileRefresher:
    """Handles automatically refreshing the user's Naukri profile."""

    def __init__(
        self,
        engine: IBrowserEngine,
        interactions: IBrowserInteractions,
    ) -> None:
        self._engine = engine
        self._interactions = interactions

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

            logger.info("Waiting for Resume Headline edit icon...")
            # Wait for the edit icon to be attached
            edit_icon = page.locator(ProfileSelectors.RESUME_HEADLINE_EDIT_ICON).first
            await edit_icon.wait_for(state="attached", timeout=NAVIGATION_TIMEOUT)

            # Add a small delay for any overlay or rendering to settle
            await asyncio.sleep(2)

            logger.info("Clicking Resume Headline edit icon...")
            # Use interactions helper to click resiliently
            clicked = await self._interactions.safe_click(
                ProfileSelectors.RESUME_HEADLINE_EDIT_ICON, timeout=10_000
            )

            if not clicked:
                log_error("Failed to click the resume headline edit icon.")
                return False

            logger.info("Waiting for Save button in modal...")
            save_button = page.locator(ProfileSelectors.SAVE_BUTTON).first
            await save_button.wait_for(state="visible", timeout=10_000)

            # Small delay before saving to mimic human behavior
            await asyncio.sleep(1.5)

            logger.info("Clicking Save button...")
            saved = await self._interactions.safe_click(
                ProfileSelectors.SAVE_BUTTON, timeout=10_000
            )

            if not saved:
                log_error("Failed to click the save button.")
                return False

            # Wait for the modal to close or a brief moment to ensure save goes through
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
            return False
