"""
Human-like interaction utilities for browser automation.
Separates interaction logic from core browser lifecycle management.
"""

from __future__ import annotations

import asyncio
import random


from src.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.config.constants import ELEMENT_TIMEOUT, DEFAULT_TIMEOUT
from src.config.settings import Settings
from src.utils.helpers import random_delay
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HumanInteractions(IBrowserInteractions):
    """
    Implements human-like interactions on top of a browser engine.
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
        """Type text character by character with random inter-key delays."""
        element = await self._engine.page.wait_for_selector(selector, timeout=ELEMENT_TIMEOUT)
        if element is None:
            raise RuntimeError(f"Element not found: {selector}")

        if clear_first:
            await element.click(force=True)
            await self._engine.page.keyboard.press("Control+a")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await self._engine.page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.2, 0.5))

        for char in text:
            await element.type(char, delay=random.randint(50, 150))
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.8))

    async def safe_click(
        self,
        selector: str,
        timeout: int = ELEMENT_TIMEOUT,
        force: bool = False,
    ) -> bool:
        """Click an element safely with human-like pre-click delay."""
        try:
            await asyncio.sleep(random.uniform(0.3, 0.8))

            element = await self._engine.page.wait_for_selector(
                selector, timeout=timeout, state="visible"
            )
            if element is None:
                return False

            await element.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.2, 0.5))

            if force:
                await element.click(force=True)
            else:
                await element.click()

            return True
        except Exception as e:
            logger.debug(f"safe_click failed for '{selector}': {e}")
            return False

    async def js_click(self, selector: str) -> bool:
        """Click an element via JavaScript (bypasses overlays)."""
        try:
            await self._engine.page.evaluate(
                """(selector) => {
                    const el = document.querySelector(selector);
                    if (el) { el.click(); return true; }
                    return false;
                }""",
                selector,
            )
            return True
        except Exception as e:
            logger.debug(f"js_click failed for '{selector}': {e}")
            return False

    async def random_scroll(self, scroll_count: int = 3) -> None:
        """Scroll the page randomly to simulate human reading behavior."""
        for _ in range(scroll_count):
            direction = random.choice(["down", "down", "up"])
            distance = random.randint(100, 500)
            if direction == "up":
                distance = -distance

            await self._engine.page.evaluate(f"window.scrollBy(0, {distance})")
            await asyncio.sleep(random.uniform(0.5, 1.5))

    async def close_popups(self) -> None:
        """Attempt to close any visible popups or modals."""
        popup_selectors = [
            '//button[@aria-label="Close"]',
            '//button[contains(@class, "close")]',
            '//span[contains(@class, "close")]',
            '[class*="chatbot-close"]',
            '[class*="modal-close"]',
            '[class*="crossIcon"]',
        ]

        for selector in popup_selectors:
            try:
                element = await self._engine.page.query_selector(selector)
                if element and await element.is_visible():
                    await element.click()
                    logger.debug(f"Closed popup with selector: {selector}")
                    await asyncio.sleep(0.5)
            except Exception:
                pass

    async def wait_for_navigation_complete(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Wait for the page to finish loading."""
        try:
            await self._engine.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            try:
                await self._engine.page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except Exception:
                logger.debug("Navigation wait timed out, continuing anyway")

    async def action_delay(self) -> None:
        """Insert a configurable random delay between browser actions."""
        await random_delay(
            self._settings.application.delay_between_actions_min,
            self._settings.application.delay_between_actions_max,
        )

    async def get_text_content(self, selector: str) -> str:
        """Get text content of an element, returning empty string on failure."""
        try:
            element = await self._engine.page.query_selector(selector)
            if element:
                return (await element.text_content() or "").strip()
        except Exception:
            pass
        return ""

    async def element_exists(self, selector: str) -> bool:
        """Check if an element exists on the page."""
        try:
            element = await self._engine.page.query_selector(selector)
            return element is not None
        except Exception:
            return False
