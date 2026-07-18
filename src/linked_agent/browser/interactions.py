"""
Human-like interaction utilities for LinkedIn browser automation.
Separates interaction logic from core browser lifecycle management.

LinkedIn has stricter anti-automation detection, so delays are longer
and interactions are more deliberately human-like.
"""

from __future__ import annotations

import asyncio
import random

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.linked_agent.config.constants import (
    DEFAULT_TIMEOUT,
    ELEMENT_TIMEOUT,
    LINKEDIN_MIN_DELAY_BETWEEN_ACTIONS,
    LINKEDIN_MAX_DELAY_BETWEEN_ACTIONS,
)
from src.linked_agent.config.settings import Settings
from src.linked_agent.bot.interfaces import IBrowserEngine, IBrowserInteractions
from src.linked_agent.utils.helpers import TimeUtility
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInHumanInteractions(IBrowserInteractions):
    """
    Implements human-like interactions on top of a browser engine.
    LinkedIn-specific with longer, more realistic delays.
    """

    def __init__(self, engine: IBrowserEngine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings

    async def human_type(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
    ) -> None:
        """Type text into an input field reliably using fill() then press_sequentially()."""
        page = self._engine.page
        locator = page.locator(selector)

        # Wait for element to be visible
        try:
            await locator.first.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        except PlaywrightTimeoutError:
            raise RuntimeError(f"Element not found or not visible: {selector}")

        if clear_first:
            await locator.first.click(force=True)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.3, 0.5))

        # Use fill() for reliable value setting, then dispatch input event
        await locator.first.fill(text)
        await page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }""",
            selector.split(",")[0].strip(),
        )

    async def safe_click(
        self,
        selector: str,
        timeout: int = ELEMENT_TIMEOUT,
        force: bool = False,
    ) -> bool:
        """Click an element safely with human-like pre-click delay."""
        try:
            await asyncio.sleep(random.uniform(0.5, 1.2))

            element = await self._engine.page.wait_for_selector(
                selector, timeout=timeout, state="visible"
            )
            if element is None:
                return False

            await element.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.3, 0.8))

            if force:
                await element.click(force=True)
            else:
                await element.click()

            return True
        except PlaywrightError as e:
            logger.debug(f"safe_click failed for '{selector}': {e}")
            return False

    async def random_scroll(self, scroll_count: int = 3) -> None:
        """Scroll the page randomly to simulate human reading behavior."""
        for _ in range(scroll_count):
            direction = random.choice(["down", "down", "up"])
            distance = random.randint(100, 400)
            if direction == "up":
                distance = -distance

            await self._engine.page.evaluate(f"window.scrollBy(0, {distance})")
            await asyncio.sleep(random.uniform(0.8, 2.0))

    async def close_popups(self) -> None:
        """Attempt to close any visible popups or modals on LinkedIn."""
        page = self._engine.page
        if not page:
            return

        # 1. Try Escape key
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except PlaywrightError:
            pass

        # 2. LinkedIn-specific close button selectors
        popup_selectors = [
            "button[aria-label='Dismiss' i]",
            "button[aria-label='Close' i]",
            "button:has-text('Dismiss')",
            "button:has-text('Close')",
            "button:has-text('No thanks')",
            "button:has-text('Not now')",
            "button:has-text('Skip')",
            "button.artdeco-modal__dismiss",
            "li-icon[name='close']",
            "div[role='dialog'] button[aria-label='Dismiss' i]",
            "div[role='dialog'] button[aria-label='Close' i]",
            "button[data-test='dismiss']",
            "button[data-control-name='overlay.close']",
        ]

        for selector in popup_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=500):
                    await locator.click(timeout=1500)
                    logger.debug(f"Closed LinkedIn popup with selector: {selector}")
                    await asyncio.sleep(0.5)
            except (PlaywrightTimeoutError, PlaywrightError):
                pass

        # 3. Remove overlay backdrops
        try:
            await page.evaluate("""() => {
                const overlays = document.querySelectorAll('.artdeco-modal-overlay, .artdeco-toast-item, [data-test="modal-container"]');
                overlays.forEach(el => el.remove());
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            }""")
        except PlaywrightError:
            pass

    async def wait_for_navigation_complete(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Wait for the page to finish loading."""
        try:
            await self._engine.page.wait_for_load_state("networkidle", timeout=timeout)
        except PlaywrightTimeoutError:
            try:
                await self._engine.page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except PlaywrightTimeoutError:
                logger.debug("Navigation wait timed out, continuing anyway")

    async def action_delay(self) -> None:
        """Insert a configurable random delay between browser actions."""
        await TimeUtility.random_delay(
            LINKEDIN_MIN_DELAY_BETWEEN_ACTIONS,
            LINKEDIN_MAX_DELAY_BETWEEN_ACTIONS,
        )

    async def get_text_content(self, selector: str) -> str:
        """Get text content of an element, returning empty string on failure."""
        try:
            element = await self._engine.page.query_selector(selector)
            if element:
                return (await element.text_content() or "").strip()
        except PlaywrightError:
            pass
        return ""

    async def element_exists(self, selector: str) -> bool:
        """Check if an element exists on the page."""
        try:
            element = await self._engine.page.query_selector(selector)
            return element is not None
        except PlaywrightError:
            return False
