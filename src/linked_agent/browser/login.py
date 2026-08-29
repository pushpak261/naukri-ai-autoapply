"""
LinkedIn login flow handler.

Manages the complete login lifecycle:
1. Attempt session restoration from saved storage state
2. If session expired: navigate to login, enter credentials
3. Handle 2FA if prompted
4. Validate login success
5. Save session state for future reuse
"""

from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.linked_agent.browser.pages.login import LinkedInLoginPage
from src.linked_agent.config.settings import Settings
from src.linked_agent.bot.interfaces import IBrowserEngine, ILoginStrategy
from src.linked_agent.utils.logger import (
    console,
    get_logger,
    log_error,
    log_info,
    log_success,
    log_warning,
)

logger = get_logger(__name__)


class LinkedInPasswordLoginStrategy(ILoginStrategy):
    """Executes the standard Email + Password login flow for LinkedIn."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def authenticate(self, login_page: LinkedInLoginPage) -> bool:
        log_info("Executing LinkedIn Email & Password login flow...")

        email = self._settings.linkedin.email
        if not email:
            log_error("LinkedIn email not configured. Set LINKEDIN_EMAIL in .env or linkedin.email in config")
            return False

        password = self._settings.linkedin.password
        if not password:
            log_error("LinkedIn password not configured. Set LINKEDIN_PASSWORD in .env or linkedin.password in config")
            return False

        await login_page.fill_credentials(email, password)
        await login_page.submit_login()

        # Check for 2FA requirement
        await asyncio.sleep(3)
        if await login_page.detect_2fa_input():
            log_warning("LinkedIn 2FA verification required!")
            console.print(
                "\n  [bold yellow]2FA REQUIRED[/bold yellow]\n"
                "  Please enter the verification code in the browser window.\n"
                "  The agent will wait up to 2 minutes.\n",
            )

            # Check if auto 2FA code is configured
            two_factor_code = self._settings.linkedin.two_factor_code
            if two_factor_code:
                log_info("Using configured 2FA code...")
                await login_page.fill_2fa(two_factor_code)
                await login_page.submit_2fa()
                await asyncio.sleep(5)
            else:
                # Wait for manual 2FA entry
                for _ in range(24):
                    await asyncio.sleep(5)
                    try:
                        if not await login_page.detect_2fa_input():
                            return True
                    except Exception:
                        return True
                log_warning("2FA wait timed out after 2 minutes")

        return True


class LinkedInLoginHandler:
    """
    Handles LinkedIn login with 2FA support using login strategies.

    Usage:
        strategy = LinkedInPasswordLoginStrategy(settings)
        handler = LinkedInLoginHandler(login_page, engine, strategy=strategy)
        success = await handler.login()
    """

    def __init__(
        self,
        login_page: LinkedInLoginPage,
        engine: IBrowserEngine,
        strategy: ILoginStrategy | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._login_page = login_page
        self._engine = engine
        self._strategy = strategy
        self._settings = settings
        if self._strategy is None:
            raise ValueError("A login strategy must be provided. Use LinkedInLoginHandler.create() factory method.")

    @classmethod
    def create(
        cls,
        login_page: LinkedInLoginPage,
        engine: IBrowserEngine,
        settings: Settings,
    ) -> LinkedInLoginHandler:
        """Factory method to create a properly configured handler."""
        strategy = LinkedInPasswordLoginStrategy(settings)
        return cls(login_page=login_page, engine=engine, strategy=strategy, settings=settings)

    async def login(self) -> bool:
        """
        Execute the full LinkedIn login flow.
        First checks if a saved session is still valid.
        """
        if await self._check_existing_session():
            log_success("LinkedIn session restored — already logged in!")
            self._engine.mark_session_authenticated()
            return True

        log_info("Starting fresh LinkedIn login...")
        return await self._perform_login()

    async def _check_existing_session(self) -> bool:
        """Navigate to LinkedIn and check if saved session is valid."""
        try:
            await self._login_page.navigate_to_base()
            is_logged_in = await self._login_page.is_logged_in()
            if is_logged_in:
                return True
            logger.info("LinkedIn saved session expired or not found")
            return False
        except (PlaywrightTimeoutError, PlaywrightError) as e:
            logger.debug(f"LinkedIn session check failed: {e}")
            return False

    async def _perform_login(self) -> bool:
        """Perform a fresh LinkedIn login."""
        try:
            log_info("Navigating to LinkedIn login page...")
            await self._login_page.navigate()
            await asyncio.sleep(2)
            await self._login_page.close_popups()

            log_info(f"Email configured: {'Yes' if self._settings.linkedin.email else 'No'}")
            log_info(f"Password configured: {'Yes' if self._settings.linkedin.password else 'No'}")

            success = await self._strategy.authenticate(self._login_page)
            if not success:
                log_error("LinkedIn login strategy failed")
                return False

            log_info("Verifying LinkedIn login state...")
            await self._login_page.wait_for_navigation_settle()

            verified, reason = await self._login_page.verify_auth_state()

            if verified:
                log_success("LinkedIn login successful!")
                await self._engine.save_session()
                return True

            log_warning(f"LinkedIn auth verification failed: {reason}")

            error_text = await self._login_page.get_login_error_text()
            if error_text:
                log_error(f"LinkedIn login error: {error_text}")
            elif await self._login_page.has_captcha():
                log_error("CAPTCHA challenge detected — LinkedIn login blocked")
            elif await self._login_page.is_on_login_page():
                log_error("LinkedIn login failed — still on login page")
            else:
                log_error("LinkedIn login failed — could not verify authenticated state")

            return False

        except (PlaywrightTimeoutError, PlaywrightError) as e:
            error_msg = str(e)
            if "Target page, context or browser has been closed" in error_msg:
                log_error("Browser was closed by the user. Aborting LinkedIn login.")
            else:
                log_error(f"LinkedIn login failed with error: {e}")
                logger.exception("LinkedIn login exception details")
            return False
        except RuntimeError as e:
            log_error(f"LinkedIn login runtime error: {e}")
            logger.exception("LinkedIn login runtime exception details")
            return False
