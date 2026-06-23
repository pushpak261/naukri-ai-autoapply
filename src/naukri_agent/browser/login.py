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

from src.naukri_agent.browser.pages.login import LoginPage
from src.naukri_agent.config.constants import LOGIN_TIMEOUT
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.interfaces import IBrowserEngine
from src.naukri_agent.utils.gmail_otp import fetch_naukri_otp
from src.naukri_agent.utils.logger import (
    console,
    get_logger,
    log_error,
    log_info,
    log_success,
    log_warning,
)

logger = get_logger(__name__)


class LoginHandler:
    """
    Handles Naukri.com login with OTP support.

    Designed for supervised use — the browser is visible, and the user
    must manually enter OTP when prompted.

    Usage:
        handler = LoginHandler(login_page, engine, settings)
        success = await handler.login()
    """

    def __init__(self, login_page: LoginPage, engine: IBrowserEngine, settings: Settings) -> None:
        self._login_page = login_page
        self._engine = engine
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
            await self._login_page.navigate_to_base()

            # Check for profile indicators (logged-in state)
            is_logged_in = await self._login_page.is_logged_in()
            if is_logged_in:
                return True

            logger.info("Saved session expired or not found")
            return False

        except Exception as e:
            logger.debug(f"Session check failed: {e}")
            return False

    async def _perform_login(self) -> bool:
        """
        Perform a fresh login using either direct OTP or Password authentication.
        """
        try:
            # Navigate to login page
            log_info("Navigating to Naukri login page...")
            await self._login_page.navigate()

            # Close any popups
            await self._login_page.close_popups()

            # Choose the modular login path
            if self._settings.naukri.use_otp_login:
                success = await self._login_with_otp()
            else:
                success = await self._login_with_password()

            if not success:
                return False

            # Validate login
            if await self._login_page.is_logged_in():
                log_success("Login successful! 🎉")
                await self._engine.save_session()
                return True
            else:
                # Check for error messages
                error_text = await self._login_page.get_login_error_text()
                if error_text:
                    log_error(f"Login failed: {error_text}")
                else:
                    log_error("Login failed — could not verify logged-in state")
                return False

        except Exception as e:
            error_msg = str(e)
            if "Target page, context or browser has been closed" in error_msg:
                log_error("Browser was closed by the user. Aborting login.")
            else:
                log_error(f"Login failed with error: {e}")
                logger.exception("Login exception details")
            return False

    async def _login_with_password(self) -> bool:
        """Execute the standard Email + Password login flow."""
        log_info("Executing Email & Password login flow...")

        # Enter email
        log_info("Entering email...")
        email = self._settings.naukri.email
        if not email:
            log_error("Naukri email not configured. Set NAUKRI_EMAIL in .env or config.yaml")
            return False

        # Enter password
        log_info("Entering password...")
        password = self._settings.naukri.password
        if not password:
            log_error("Naukri password not configured. Set NAUKRI_PASSWORD in .env or config.yaml")
            return False

        await self._login_page.fill_credentials(email, password)
        await self._login_page.submit_password_login()

        # Check for OTP requirement (Naukri sometimes challenges password login with OTP)
        await self._handle_otp()
        return True

    async def _login_with_otp(self) -> bool:
        """Execute the direct Mobile Number + OTP login flow."""
        log_info("Executing direct OTP login via Mobile Number...")

        # Click the "Use OTP to Login" link/button
        log_info("Switching to OTP Login form...")
        await self._login_page.switch_to_otp_login()

        # Enter mobile number
        mobile_number = self._settings.naukri.mobile_number
        if not mobile_number:
            log_error(
                "Mobile number not configured. Set NAUKRI_MOBILE_NUMBER in .env or config.yaml"
            )
            return False

        log_info(f"Entering mobile number: {mobile_number}...")
        await self._login_page.fill_mobile_number(mobile_number)

        # Click the "Get OTP" button
        log_info("Clicking Get OTP button...")
        await self._login_page.click_get_otp()

        # Handle the automatic/manual OTP entry
        await self._handle_otp()
        return True

    async def _handle_otp(self) -> None:
        """
        Check for OTP input field and wait for user to enter it manually or
        fetch it automatically from Gmail if credentials are provided.
        """
        try:
            # Check if OTP field appeared
            otp_field_visible = await self._login_page.detect_otp_input()

            if otp_field_visible:
                gmail_email = self._settings.naukri.gmail_otp_email
                gmail_password = self._settings.naukri.gmail_app_password

                # Check if automated Gmail OTP retrieval is configured
                if gmail_email and gmail_password:
                    log_info(
                        "Gmail OTP credentials found. Attempting to fetch OTP automatically..."
                    )

                    # Fetch OTP in a background thread to avoid blocking the asyncio event loop
                    otp = await asyncio.to_thread(fetch_naukri_otp, gmail_email, gmail_password)

                    if otp:
                        log_info("Filling in the automatically retrieved OTP...")
                        # Type OTP
                        await self._login_page.fill_otp(otp)

                        # Click verify/submit
                        log_info("Submitting OTP...")
                        await self._login_page.submit_otp()

                        # Wait to see if we navigate to logged-in state successfully
                        await asyncio.sleep(5)
                        if await self._login_page.is_logged_in():
                            log_success("OTP verified automatically!")
                            return
                        else:
                            log_warning(
                                "Automatic OTP verification did not succeed. Falling back to manual entry..."
                            )
                    else:
                        log_warning(
                            "Could not retrieve OTP from Gmail. Falling back to manual entry..."
                        )

                log_warning("OTP required! Please enter the OTP in the browser window.")
                console.print(
                    "\n  🔐 [bold yellow]OTP REQUIRED[/bold yellow]\n"
                    "  Please enter the OTP sent to your registered email/phone\n"
                    "  in the browser window. The agent will wait up to 2 minutes.\n",
                )

                # Wait for navigation (OTP submission will navigate)
                success = await self._login_page.wait_for_otp_success(LOGIN_TIMEOUT)
                if success:
                    log_success("OTP accepted!")
                else:
                    log_warning("OTP wait timed out after 2 minutes")
            else:
                logger.debug("No OTP field detected — direct login")

        except Exception as e:
            logger.debug(f"OTP handling note: {e}")
