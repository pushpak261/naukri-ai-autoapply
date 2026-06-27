"""
Human-like interaction utilities for browser automation.
Separates interaction logic from core browser lifecycle management.
"""

from __future__ import annotations

import asyncio
import random

from src.naukri_agent.config.constants import DEFAULT_TIMEOUT, ELEMENT_TIMEOUT
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.naukri_agent.utils.helpers import random_delay
from src.naukri_agent.utils.logger import get_logger

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
        page = self._engine.page
        if not page:
            return

        # 1. Try Escape key
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
        except Exception:
            pass

        # 2. Try close button selectors
        popup_selectors = [
            "img[alt='cross-icon' i]",
            "[alt*='cross' i]",
            "[alt*='close' i]",
            "button[aria-label='Close' i]",
            "[aria-label='close' i]",
            "div[class*='modal' i] svg",  # the X icon is often a bare svg
            "div[class*='modal' i] [class*='close' i]",
            "div[class*='overlay' i] [class*='close' i]",
            "[class*='cross' i]",
            "[class*='close' i]",
            "[class*='chatbot-close' i]",
            "[class*='modal-close' i]",
            "[class*='popup-close' i]",
            "[class*='crossIcon' i]",
            "button:has-text('Close')",
            "button:has-text('Dismiss')",
            "button:has-text('No thanks')",
            "button:has-text('Not now')",
            "button:has-text('Skip')",
        ]

        for selector in popup_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=500):
                    await locator.click(timeout=1500)
                    logger.debug(f"Closed popup with selector: {selector}")
                    await asyncio.sleep(0.4)
            except Exception:
                pass

        # 3. Fallback: Hiding/removing overlays using DOM injection (excluding elements with Save button)
        try:
            popup_container_selectors = [
                ".nps-feedback-container",
                ".md__backdrop",
                ".npsf__captureNpsPopup",
                "[class*='modal' i]",
                "[class*='overlay' i]",
                "[class*='popup' i]",
                "[class*='backdrop' i]",
                "[class*='nps' i]",
            ]
            for container_sel in popup_container_selectors:
                elements_removed = await page.evaluate(
                    f"""() => {{
                    let count = 0;
                    document.querySelectorAll("{container_sel}").forEach(el => {{
                        if (!el) return;
                        // Avoid removing the edit modal (which contains a Save button)
                        const hasSaveButton = Array.from(el.querySelectorAll('button')).some(
                            btn => btn.textContent.trim().toLowerCase() === 'save'
                        );
                        if (!hasSaveButton && !el.contains(document.querySelector('.profile-summary')) && !el.id.includes('root')) {{
                            el.remove();
                            count++;
                        }}
                    }});
                    // Restore body overflow style in case modal disabled scrolling
                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                    return count;
                }}"""
                )
                if elements_removed > 0:
                    logger.debug(
                        f"Programmatically removed {elements_removed} blocking elements matching '{container_sel}'"
                    )
        except Exception as e:
            logger.debug(f"Error removing overlays via JS fallback: {e}")

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
