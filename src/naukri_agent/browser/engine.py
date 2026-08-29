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
    Error as PlaywrightError,
)

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

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

        try:
            self._playwright = await async_playwright().start()

            # Resolve headless mode:
            #   - Explicit override via HEADLESS env (true/false/1/0/yes/no).
            #   - Default: headed when a graphical display is available
            #     (desktop supervision, harder for Akamai to block) and
            #     headless only on display-less servers. This agent is
            #     designed for supervised use, so we prefer a real window.
            headless_env = os.environ.get("HEADLESS", "").lower()
            if headless_env in ("true", "1", "yes"):
                is_headless = True
            elif headless_env in ("false", "0", "no"):
                is_headless = False
            else:
                is_headless = not os.environ.get("DISPLAY") and sys.platform != "win32"

            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu",
            ]
            if not is_headless:
                launch_args.append("--start-maximized")

            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=is_headless,
                    args=launch_args,
                )
            except Exception as launch_err:
                if "Executable doesn't exist" in str(launch_err) or "playwright install" in str(launch_err) or "EPIPE" in str(launch_err):
                    import subprocess
                    logger.info("Installing Playwright Chromium dependencies...")
                    subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=False)
                    self._browser = await self._playwright.chromium.launch(
                        headless=is_headless,
                        args=launch_args,
                    )
                else:
                    raise launch_err

            # Create context with session restoration
            context_options: dict[str, object] = {
                "user_agent": DEFAULT_USER_AGENT,
                "locale": DEFAULT_LOCALE,
                "timezone_id": DEFAULT_TIMEZONE,
                "permissions": [],
                "java_script_enabled": True,
                "bypass_csp": False,
                "ignore_https_errors": False,
            }
            if is_headless:
                context_options["viewport"] = {"width": 1920, "height": 1080}
            else:
                context_options["no_viewport"] = True


            # Restore session state if available (handles encrypted files)
            if self._session_path and self._session_path.exists():
                logger.info("Restoring previous session state...")
                try:
                    raw = self._session_path.read_bytes()
                    decrypted = self._decrypt(raw)
                    state = json.loads(decrypted.decode("utf-8"))
                    if state.get("cookies") or state.get("origins"):
                        context_options["storage_state"] = state
                except Exception:
                    logger.warning("Failed to load session state, treating as plaintext path")
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

            if self._stealth_patcher:
                await self._stealth_patcher.apply(self._page)

            logger.info("Browser launched successfully")
            return self._page
        except PlaywrightError as e:
            logger.error(f"Failed to launch browser: {e}")
            await self.close()
            raise BrowserAutomationError(f"Playwright failed to start: {e}") from e

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
