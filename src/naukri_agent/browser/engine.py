"""
Playwright browser lifecycle manager for the Naukri Agent.

Handles browser launch, context creation, page management, and provides
utility methods for human-like interactions (typing, clicking, scrolling)
with built-in random delays.
"""

from __future__ import annotations

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from src.naukri_agent.browser.stealth import apply_stealth_scripts
from src.naukri_agent.config.constants import (
    DEFAULT_LOCALE,
    DEFAULT_TIMEOUT,
    DEFAULT_TIMEZONE,
    DEFAULT_USER_AGENT,
)
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.exceptions import BrowserAutomationError
from src.naukri_agent.core.interfaces import IBrowserEngine
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


class PlaywrightEngine(IBrowserEngine):
    """
    Manages the Playwright browser lifecycle.

    Key features:
    - Persistent browser context with session state reuse
    - Anti-detection stealth patches

    Usage:
        engine = PlaywrightEngine(settings)
        await engine.launch()
        page = engine.page
        await engine.close()
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._session_path = settings.sessions_dir / "naukri_session.json"

    @property
    def page(self) -> Page:
        """The active browser page. Raises if not launched."""
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """The browser context. Raises if not launched."""
        if self._context is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._context

    async def launch(self) -> Page:
        """
        Launch the browser with stealth configuration.

        If a saved session state exists, it will be loaded to restore
        cookies and local storage (avoiding re-login).

        Returns:
            The active Page instance.
        """
        logger.info("Launching browser...")

        try:
            self._playwright = await async_playwright().start()

            # Launch visible (non-headless) Chromium
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--start-maximized",
                ],
            )

            # Create context with session restoration
            context_options: dict[str, object] = {
                "no_viewport": True,
                "user_agent": DEFAULT_USER_AGENT,
                "locale": DEFAULT_LOCALE,
                "timezone_id": DEFAULT_TIMEZONE,
                "permissions": [],
                "java_script_enabled": True,
                "bypass_csp": False,
                "ignore_https_errors": False,
            }

            # Restore session state if available
            if self._session_path.exists():
                logger.info("Restoring previous session state...")
                context_options["storage_state"] = str(self._session_path)

            # NOTE: Playwright's new_context() has a long overloaded signature;
            # mypy can't verify a dynamically-built kwargs dict against it.
            # The keys above are all valid BrowserContext options.
            self._context = await self._browser.new_context(**context_options)  # type: ignore[arg-type]

            # Set default timeouts
            self._context.set_default_timeout(DEFAULT_TIMEOUT)
            self._context.set_default_navigation_timeout(DEFAULT_TIMEOUT)

            # Create page and apply stealth
            self._page = await self._context.new_page()

            await apply_stealth_scripts(self._page)

            logger.info("Browser launched successfully")
            return self._page
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            await self.close()
            raise BrowserAutomationError(f"Playwright failed to start: {e}") from e

    async def save_session(self) -> None:
        """Save the current browser session state (cookies, local storage)."""
        if self._context:
            self._session_path.parent.mkdir(parents=True, exist_ok=True)
            state = await self._context.storage_state()
            import json

            with open(self._session_path, "w", encoding="utf-8") as f:
                json.dump(state, f)
            logger.debug("Session state saved")

    async def close(self) -> None:
        """Save session and close all browser resources."""
        try:
            await self.save_session()
        except Exception as e:
            logger.warning(f"Failed to save session state: {e}")

        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        logger.info("Browser closed")

    def is_alive(self) -> bool:
        """Check if the browser and page are still connected/open."""
        if self._browser is None or not self._browser.is_connected():
            return False
        return not (self._page is None or self._page.is_closed())
