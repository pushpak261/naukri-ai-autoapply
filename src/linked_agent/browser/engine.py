"""
Playwright browser lifecycle manager for the LinkedIn Agent.

Handles browser launch, context creation, page management, and session
persistence with Fernet encryption. LinkedIn-specific configuration
includes enhanced stealth and stricter rate limiting.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
    Error as PlaywrightError,
)
from cryptography.fernet import Fernet

from src.linked_agent.config.constants import (
    DEFAULT_LOCALE,
    DEFAULT_TIMEOUT,
    DEFAULT_TIMEZONE,
    DEFAULT_USER_AGENT,
)
from src.linked_agent.config.settings import Settings
from src.linked_agent.utils.exceptions import BrowserAutomationError
from src.linked_agent.bot.interfaces import IBrowserEngine, IStealthPatcher
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInPlaywrightEngine(IBrowserEngine):
    """
    Manages the Playwright browser lifecycle for LinkedIn automation.

    Key features:
    - Persistent browser context with session state reuse
    - LinkedIn-specific anti-detection stealth patches
    - Encrypted session storage (Fernet)
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

        # Configure default session path if email is configured
        if settings.linkedin.email:
            self.set_session_for_account(settings.linkedin.email)

    def set_session_for_account(self, account_email: str) -> None:
        """Switch session to a specific account's saved state."""
        safe_name = account_email.replace("@", "_at_").replace(".", "_dot_")
        self._session_path = self._settings.sessions_dir / f"linkedin_session_{safe_name}.json"

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

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._context

    async def launch(self) -> Page:
        """
        Launch the browser with LinkedIn-specific stealth configuration.
        """
        logger.info("Launching browser for LinkedIn automation...")
        self._session_saved = False

        try:
            self._playwright = await async_playwright().start()

            is_headless = os.environ.get("HEADLESS", "").lower() in ("true", "1", "yes") or not os.environ.get("DISPLAY")
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu",
                "--start-maximized",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ]

            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=is_headless,
                    args=launch_args,
                )
            except Exception as launch_err:
                if "Executable doesn't exist" in str(launch_err) or "playwright install" in str(launch_err):
                    import subprocess
                    import sys
                    logger.info("Chromium not installed. Auto-installing Playwright Chromium...")
                    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                    self._browser = await self._playwright.chromium.launch(
                        headless=is_headless,
                        args=launch_args,
                    )
                else:
                    raise launch_err


            # LinkedIn-specific context options
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
            if self._session_path and self._session_path.exists():
                logger.info("Restoring previous LinkedIn session...")
                try:
                    raw = self._session_path.read_bytes()
                    decrypted = self._decrypt(raw)
                    state = json.loads(decrypted.decode("utf-8"))
                    if state.get("cookies") or state.get("origins"):
                        context_options["storage_state"] = state
                except Exception:
                    logger.warning("Failed to load session state, treating as plaintext path")
                    context_options["storage_state"] = str(self._session_path)

            self._context = await self._browser.new_context(**context_options)  # type: ignore[arg-type]

            self._context.set_default_timeout(DEFAULT_TIMEOUT)
            self._context.set_default_navigation_timeout(DEFAULT_TIMEOUT)

            self._page = await self._context.new_page()

            if self._stealth_patcher:
                await self._stealth_patcher.apply(self._page)

            logger.info("Browser launched successfully for LinkedIn")
            return self._page
        except PlaywrightError as e:
            logger.error(f"Failed to launch browser: {e}")
            await self.close()
            raise BrowserAutomationError(f"Playwright failed to start: {e}") from e

    async def save_session(self) -> None:
        """Save the current browser session state — encrypted at rest."""
        if self._context and self._session_path:
            self._session_path.parent.mkdir(parents=True, exist_ok=True)
            state = await self._context.storage_state()
            raw = json.dumps(state, ensure_ascii=False).encode("utf-8")
            self._session_path.write_bytes(self._encrypt(raw))
            self._session_saved = True
            logger.debug("LinkedIn session state saved")

    def mark_session_authenticated(self) -> None:
        self._session_saved = True

    async def close(self) -> None:
        """Save session and close all browser resources."""
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
        if self._browser is None or not self._browser.is_connected():
            return False
        return not (self._page is None or self._page.is_closed())
