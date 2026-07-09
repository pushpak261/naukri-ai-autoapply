"""
Playwright browser lifecycle manager for the Naukri Agent.

Handles browser launch, context creation, page management, and provides
utility methods for human-like interactions (typing, clicking, scrolling)
with built-in random delays.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
    Error as PlaywrightError,
)

import base64
import hashlib
import json

from cryptography.fernet import Fernet

from src.naukri_agent.config.constants import (
    DEFAULT_LOCALE,
    DEFAULT_TIMEOUT,
    DEFAULT_TIMEZONE,
    DEFAULT_USER_AGENT,
)
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.utils.exceptions import BrowserAutomationError
from src.naukri_agent.bot.interfaces import IBrowserEngine, IStealthPatcher
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WorkerBrowser:
    """Isolated browser context + page for one apply worker."""

    context: BrowserContext
    page: Page
    worker_id: int

    async def close(self) -> None:
        try:
            if not self.page.is_closed():
                await self.page.close()
        except Exception as e:
            logger.debug(f"Worker-{self.worker_id} page close error: {e}")
        try:
            await self.context.close()
        except Exception as e:
            logger.debug(f"Worker-{self.worker_id} context close error: {e}")


class WorkerBrowserEngine:
    """IBrowserEngine subset for a single worker tab (no launch/close lifecycle)."""

    def __init__(self, worker: WorkerBrowser) -> None:
        self._worker = worker

    @property
    def page(self) -> Page:
        return self._worker.page

    @property
    def context(self) -> BrowserContext:
        return self._worker.context

    def is_alive(self) -> bool:
        return not self._worker.page.is_closed()

    async def launch(self) -> Page:
        return self._worker.page

    async def save_session(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def set_session_for_account(self, account_email: str) -> None:
        return None

    def mark_session_authenticated(self) -> None:
        return None


class PlaywrightEngine(IBrowserEngine):
    """
    Manages the Playwright browser lifecycle.

    Key features:
    - Persistent browser context with session state reuse
    - Anti-detection stealth patches
    - Optional isolated worker contexts cloned from logged-in session

    Usage:
        engine = PlaywrightEngine(settings)
        await engine.launch()
        page = engine.page
        await engine.close()
    """

    def __init__(self, settings: Settings, stealth_patcher: IStealthPatcher | None = None) -> None:
        self._settings = settings
        self._stealth_patcher = stealth_patcher
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._session_path: Path | None = None
        self._session_saved: bool = False
        self._fernet = self._init_fernet(settings)
        self._logged_in_storage_state: dict[str, Any] | None = None
        self._worker_browsers: list[WorkerBrowser] = []

    def set_session_for_account(self, account_email: str) -> None:
        """Switch session to a specific account's saved state."""
        safe_name = account_email.replace("@", "_at_").replace(".", "_dot_")
        self._session_path = self._settings.sessions_dir / f"naukri_session_{safe_name}.json"

    @staticmethod
    def _init_fernet(settings: Settings) -> Fernet | None:
        key_str = settings.session_encryption_key
        if not key_str:
            seed = str(settings.project_root).encode("utf-8")
            key_str = base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode()
        try:
            return Fernet(key_str.encode() if isinstance(key_str, str) else key_str)
        except Exception:
            logger.warning("Invalid session encryption key, falling back to plaintext storage")
            return None

    def _encrypt(self, data: bytes) -> bytes:
        if self._fernet:
            return self._fernet.encrypt(data)
        return data

    def _decrypt(self, data: bytes) -> bytes:
        if self._fernet:
            try:
                return self._fernet.decrypt(data)
            except Exception:
                logger.warning("Failed to decrypt session file, treating as plaintext")
                return data
        return data

    def _base_context_options(self) -> dict[str, object]:
        return {
            "no_viewport": True,
            "user_agent": DEFAULT_USER_AGENT,
            "locale": DEFAULT_LOCALE,
            "timezone_id": DEFAULT_TIMEZONE,
            "permissions": [],
            "java_script_enabled": True,
            "bypass_csp": False,
            "ignore_https_errors": False,
        }

    def _session_storage_for_launch(self) -> dict[str, object] | None:
        if not self._session_path or not self._session_path.exists():
            return None
        logger.info("Restoring previous session state...")
        try:
            raw = self._session_path.read_bytes()
            decrypted = self._decrypt(raw)
            state = json.loads(decrypted.decode("utf-8"))
            if state.get("cookies") or state.get("origins"):
                return state
        except Exception:
            logger.warning("Failed to load session state, treating as plaintext path")
            return {"path": str(self._session_path)}
        return None

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
        self._session_saved = False
        self._worker_browsers = []

        try:
            self._playwright = await async_playwright().start()

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

            context_options = self._base_context_options()
            storage = self._session_storage_for_launch()
            if storage is not None:
                if "path" in storage:
                    context_options["storage_state"] = storage["path"]
                else:
                    context_options["storage_state"] = storage

            self._context = await self._browser.new_context(**context_options)  # type: ignore[arg-type]
            self._context.set_default_timeout(DEFAULT_TIMEOUT)
            self._context.set_default_navigation_timeout(DEFAULT_TIMEOUT)

            self._page = await self._context.new_page()

            if self._stealth_patcher:
                await self._stealth_patcher.apply(self._page)

            logger.info("Browser launched successfully")
            return self._page
        except PlaywrightError as e:
            logger.error(f"Failed to launch browser: {e}")
            await self.close()
            raise BrowserAutomationError(f"Playwright failed to start: {e}") from e

    async def capture_logged_in_session(self) -> None:
        """Snapshot main context cookies/storage for worker context cloning."""
        if self._context is None:
            raise RuntimeError("Browser not launched")
        self._logged_in_storage_state = await self._context.storage_state()
        logger.debug("Captured logged-in storage state for worker contexts")

    async def new_worker_context(self, worker_id: int) -> WorkerBrowser:
        """New isolated context+page cloned from logged-in session."""
        if self._browser is None:
            raise RuntimeError("Browser not launched")
        if self._logged_in_storage_state is None:
            await self.capture_logged_in_session()

        context_options = self._base_context_options()
        context_options["storage_state"] = self._logged_in_storage_state
        context = await self._browser.new_context(**context_options)  # type: ignore[arg-type]
        context.set_default_timeout(DEFAULT_TIMEOUT)
        context.set_default_navigation_timeout(DEFAULT_TIMEOUT)
        page = await context.new_page()
        if self._stealth_patcher:
            await self._stealth_patcher.apply(page)

        worker = WorkerBrowser(context=context, page=page, worker_id=worker_id)
        self._worker_browsers.append(worker)
        logger.info(f"Spawned apply worker browser context Worker-{worker_id}")
        return worker

    async def close_all_worker_contexts(self) -> None:
        for worker in list(self._worker_browsers):
            await worker.close()
        self._worker_browsers.clear()

    async def refresh_worker_contexts(self) -> None:
        """Re-capture session from main context and close existing worker contexts."""
        await self.capture_logged_in_session()
        await self.close_all_worker_contexts()

    async def save_session(self) -> None:
        """Save the current browser session state (cookies, local storage) — encrypted at rest."""
        if self._context and self._session_path:
            self._session_path.parent.mkdir(parents=True, exist_ok=True)
            state = await self._context.storage_state()
            raw = json.dumps(state, ensure_ascii=False).encode("utf-8")
            self._session_path.write_bytes(self._encrypt(raw))
            self._session_saved = True
            logger.debug("Session state saved")

    def mark_session_authenticated(self) -> None:
        """
        Mark the current session as authenticated without re-saving.

        Used when a previously saved session was successfully restored
        from disk and verified as valid, so close() will persist any
        state changes made during the run.
        """
        self._session_saved = True

    async def close(self) -> None:
        """Save session and close all browser resources.

        Only saves the session if save_session() was explicitly called at
        least once during this browser lifecycle (i.e., login succeeded).
        This prevents overwriting a valid authenticated session with
        unauthenticated browser state when login fails.
        """
        await self.close_all_worker_contexts()

        if self._session_saved:
            try:
                await self.save_session()
            except Exception as e:
                logger.warning(f"Failed to save session state: {e}")
        else:
            logger.info("Skipping session save — no authenticated session was established")

        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Ignored error during browser cleanup: {e}")

        logger.info("Browser closed")

    def is_alive(self) -> bool:
        """Check if the browser and page are still connected/open."""
        if self._browser is None or not self._browser.is_connected():
            return False
        return not (self._page is None or self._page.is_closed())
