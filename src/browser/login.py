"""
Naukri.com login flow handler.

Manages the complete login lifecycle:
1. Attempt session restoration from saved storage state
2. If session expired: navigate to login, enter credentials
3. Wait for manual OTP input (supervised mode)
4. Validate login success
5. Save session state for future reuse
"""

from __future__ import annotations

import asyncio


from src.core.interfaces import IBrowserEngine, IBrowserInteractions
from src.config.constants import (
    NAUKRI_LOGIN_URL,
    NAUKRI_BASE_URL,
    LOGIN_TIMEOUT,
    LoginSelectors,
)
from src.config.settings import Settings
from src.utils.logger import get_logger, log_info, log_success, log_error, log_warning, console

logger = get_logger(__name__)


class LoginHandler:
    """
    Handles Naukri.com login with OTP support.

    Designed for supervised use — the browser is visible, and the user
    must manually enter OTP when prompted.

    Usage:
        handler = LoginHandler(engine, settings)
        success = await handler.login()
    """

    def __init__(
        self, engine: IBrowserEngine, interactions: IBrowserInteractions, settings: Settings
    ) -> None:
        self._engine = engine
        self._interactions = interactions
        self._settings = settings

    async def login(self) -> bool:
        """
        Execute the full login flow.

        First checks if a saved session is still valid. If not, performs
        a fresh login with credential entry and OTP wait.

        Returns:
            True if login was successful, False otherwise.
        """
        # Step 1: Try session restoration
        if await self._check_existing_session():
            log_success("Session restored — already logged in!")
            return True

        # Step 2: Fresh login
        log_info("Starting fresh login...")
        return await self._perform_login()

    async def _check_existing_session(self) -> bool:
        """
        Navigate to Naukri and check if saved session cookies are still valid.

        Returns:
            True if already logged in, False if session expired.
        """
        try:
            page = self._engine.page
            await page.goto(NAUKRI_BASE_URL, wait_until="domcontentloaded")
            await self._interactions.wait_for_navigation_complete()
            await asyncio.sleep(2)

            # Check for profile indicators (logged-in state)
            is_logged_in = await self._is_logged_in()
            if is_logged_in:
                return True

            logger.info("Saved session expired or not found")
            return False

        except Exception as e:
            logger.debug(f"Session check failed: {e}")
            return False

    async def _perform_login(self) -> bool:
        """
        Perform a fresh login: navigate to login page, enter credentials,
        handle OTP, and validate success.
        """
        page = self._engine.page

        try:
            # Navigate to login page
            log_info("Navigating to Naukri login page...")
            await page.goto(NAUKRI_LOGIN_URL, wait_until="domcontentloaded")
            await self._interactions.wait_for_navigation_complete()
            await asyncio.sleep(2)

            # Close any popups
            await self._interactions.close_popups()

            # Enter email
            log_info("Entering email...")
            email = self._settings.naukri.email
            if not email:
                log_error("Naukri email not configured. Set NAUKRI_EMAIL in .env or config.yaml")
                return False

            await self._interactions.human_type(LoginSelectors.EMAIL_INPUT, email)
            await self._interactions.action_delay()

            # Enter password
            log_info("Entering password...")
            password = self._settings.naukri.password
            if not password:
                log_error(
                    "Naukri password not configured. Set NAUKRI_PASSWORD in .env or config.yaml"
                )
                return False

            await self._interactions.human_type(LoginSelectors.PASSWORD_INPUT, password)
            await self._interactions.action_delay()

            # Press Enter directly inside the password field (most reliable way to submit a form)
            await page.keyboard.press("Enter")

            # Click login button as a secondary fallback
            log_info("Clicking login...")
            await self._interactions.safe_click(LoginSelectors.LOGIN_BUTTON, force=True)

            await asyncio.sleep(3)

            # Check for OTP requirement
            await self._handle_otp()

            # Validate login
            if await self._is_logged_in():
                log_success("Login successful! 🎉")
                await self._engine.save_session()
                return True
            else:
                # Check for error messages
                error_text = await self._interactions.get_text_content(LoginSelectors.LOGIN_ERROR)
                if error_text:
                    log_error(f"Login failed: {error_text}")
                else:
                    log_error("Login failed — could not verify logged-in state")
                return False

        except Exception as e:
            log_error(f"Login failed with error: {e}")
            logger.exception("Login exception details")
            return False

    async def _handle_otp(self) -> None:
        """
        Check for OTP input field and wait for user to enter it manually.

        The browser is visible, so the user can see the OTP prompt
        and enter it directly in the browser window.
        """
        page = self._engine.page

        try:
            # Check if OTP field appeared
            otp_field = await page.query_selector(LoginSelectors.OTP_INPUT)
            if not otp_field:
                # Wait a moment for it to possibly appear
                await asyncio.sleep(2)
                otp_field = await page.query_selector(LoginSelectors.OTP_INPUT)

            if otp_field:
                log_warning("OTP required! Please enter the OTP in the browser window.")
                console.print(
                    "\n  🔐 [bold yellow]OTP REQUIRED[/bold yellow]\n"
                    "  Please enter the OTP sent to your registered email/phone\n"
                    "  in the browser window. The agent will wait up to 2 minutes.\n",
                )

                # Wait for navigation (OTP submission will navigate)
                try:
                    await page.wait_for_url(
                        f"{NAUKRI_BASE_URL}/**",
                        timeout=LOGIN_TIMEOUT,
                    )
                    log_success("OTP accepted!")
                except Exception:
                    # Alternative: wait for OTP field to disappear
                    for _ in range(24):  # 24 * 5s = 120s
                        await asyncio.sleep(5)
                        otp_still_visible = await page.query_selector(LoginSelectors.OTP_INPUT)
                        if not otp_still_visible:
                            log_success("OTP accepted!")
                            return
                    log_warning("OTP wait timed out after 2 minutes")
            else:
                logger.debug("No OTP field detected — direct login")

        except Exception as e:
            logger.debug(f"OTP handling note: {e}")

    async def _is_logged_in(self) -> bool:
        """
        Check if the user is currently logged in by looking for
        profile/user indicators on the page.
        """
        page = self._engine.page

        # Explicitly check for Login buttons which mean NOT logged in
        try:
            not_logged_in = await page.query_selector('a#login_Layer, a:has-text("Login")')
            if not_logged_in and await not_logged_in.is_visible():
                return False
        except Exception:
            pass

        # Multiple checks for robustness
        checks = [
            LoginSelectors.PROFILE_ICON,
            'a[href*="mnjuser"]',
            ".nI-gNb-drawer__icon",
            'a[href*="profile/edit"]',
        ]

        for selector in checks:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    logger.debug(f"Login confirmed via selector: {selector}")
                    return True
            except Exception:
                continue

        # Additional check: look for login-specific URL patterns
        current_url = page.url
        if "nlogin" in current_url or "login" in current_url.split("?")[0]:
            return False

        # Check if we can find any user-specific element
        try:
            body_text = await page.evaluate("document.body.innerText")
            if "logout" in body_text.lower():
                return True
        except Exception:
            pass

        return False
