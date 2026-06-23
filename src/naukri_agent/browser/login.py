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
from src.naukri_agent.core.interfaces import IBrowserEngine, IOTPProvider, ILoginStrategy
from src.naukri_agent.utils.logger import (
    console,
    get_logger,
    log_error,
    log_info,
    log_success,
    log_warning,
)

logger = get_logger(__name__)


async def handle_otp_helper(login_page: LoginPage, otp_provider: IOTPProvider | None) -> None:
    """
    Check for OTP input field and wait for user to enter it manually or
    fetch it automatically from Gmail if credentials are provided.
    """
    try:
        # Check if OTP field appeared
        otp_field_visible = await login_page.detect_otp_input()

        if otp_field_visible:
            # Check if automated OTP retrieval provider is configured
            if otp_provider:
                log_info("OTP provider configured. Attempting to fetch OTP automatically...")

                otp = await otp_provider.retrieve_otp()

                if otp:
                    log_info("Filling in the automatically retrieved OTP...")
                    # Type OTP
                    await login_page.fill_otp(otp)

                    # Click verify/submit
                    log_info("Submitting OTP...")
                    await login_page.submit_otp()

                    # Wait to see if we navigate to logged-in state successfully
                    await asyncio.sleep(5)
                    if await login_page.is_logged_in():
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
            success = await login_page.wait_for_otp_success(LOGIN_TIMEOUT)
            if success:
                log_success("OTP accepted!")
            else:
                log_warning("OTP wait timed out after 2 minutes")
        else:
            logger.debug("No OTP field detected — direct login")

    except Exception as e:
        logger.debug(f"OTP handling note: {e}")


class PasswordLoginStrategy(ILoginStrategy):
    """Executes the standard Email + Password login flow."""

    def __init__(self, settings: Settings, otp_provider: IOTPProvider | None = None) -> None:
        self._settings = settings
        self._otp_provider = otp_provider

    async def authenticate(self, login_page: LoginPage) -> bool:
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

        await login_page.fill_credentials(email, password)
        await login_page.submit_password_login()

        # Check for OTP requirement (Naukri sometimes challenges password login with OTP)
        await handle_otp_helper(login_page, self._otp_provider)
        return True


class OTPLoginStrategy(ILoginStrategy):
    """Executes the direct Mobile Number + OTP login flow."""

    def __init__(self, settings: Settings, otp_provider: IOTPProvider | None = None) -> None:
        self._settings = settings
        self._otp_provider = otp_provider

    async def authenticate(self, login_page: LoginPage) -> bool:
        log_info("Executing direct OTP login via Mobile Number...")

        # Click the "Use OTP to Login" link/button
        log_info("Switching to OTP Login form...")
        await login_page.switch_to_otp_login()

        # Enter mobile number
        mobile_number = self._settings.naukri.mobile_number
        if not mobile_number:
            log_error(
                "Mobile number not configured. Set NAUKRI_MOBILE_NUMBER in .env or config.yaml"
            )
            return False

        log_info(f"Entering mobile number: {mobile_number}...")
        await login_page.fill_mobile_number(mobile_number)

        # Click the "Get OTP" button
        log_info("Clicking Get OTP button...")
        await login_page.click_get_otp()

        # Handle the automatic/manual OTP entry
        await handle_otp_helper(login_page, self._otp_provider)
        return True


class LoginHandler:
    """
    Handles Naukri.com login with OTP support using Login Strategies.

    Designed for supervised use — the browser is visible, and the user
    must manually enter OTP when prompted.

    Usage:
        strategy = PasswordLoginStrategy(settings, otp_provider)
        handler = LoginHandler(login_page, engine, strategy=strategy)
        success = await handler.login()
    """

    def __init__(
        self,
        login_page: LoginPage,
        engine: IBrowserEngine,
        settings: Settings | None = None,
        otp_provider: IOTPProvider | None = None,
        strategy: ILoginStrategy | None = None,
    ) -> None:
        self._login_page = login_page
        self._engine = engine

        if strategy is not None:
            self._strategy = strategy
        else:
            if settings is None:
                raise ValueError("Either strategy or settings must be provided.")
            if settings.naukri.use_otp_login:
                self._strategy = OTPLoginStrategy(settings, otp_provider)
            else:
                self._strategy = PasswordLoginStrategy(settings, otp_provider)

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
        Perform a fresh login using the injected login strategy.
        """
        try:
            # Navigate to login page
            log_info("Navigating to Naukri login page...")
            await self._login_page.navigate()

            # Close any popups
            await self._login_page.close_popups()

            # Delegate to strategy
            success = await self._strategy.authenticate(self._login_page)
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
