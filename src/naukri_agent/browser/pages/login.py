"""
LoginPage Page Object for Naukri.com.
Encapsulates all selectors and page-level interactions for the login page.
"""

from __future__ import annotations

import asyncio

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.config.constants import (
    NAUKRI_BASE_URL,
    NAUKRI_DASHBOARD_URL,
    NAUKRI_LOGIN_URL,
    LoginSelectors,
)
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LoginPage(BasePage):
    """
    Page Object representing the Naukri Login page.
    """

    async def navigate(self) -> None:
        """Navigate directly to the Naukri login page."""
        page = self._engine.page
        await page.goto(NAUKRI_LOGIN_URL, wait_until="domcontentloaded")
        await self._interactions.wait_for_navigation_complete()
        await asyncio.sleep(2)

    async def navigate_to_base(self) -> None:
        """Navigate to Naukri base URL to check session."""
        page = self._engine.page
        await page.goto(NAUKRI_BASE_URL, wait_until="domcontentloaded")
        await self._interactions.wait_for_navigation_complete()
        await asyncio.sleep(2)

    async def wait_and_check_logged_in(self, retries: int = 3, delay: float = 2.0) -> bool:
        """Retry the logged-in DOM check to allow slow post-login renders."""
        for attempt in range(retries):
            if await self.is_logged_in():
                return True
            if attempt < retries - 1:
                await asyncio.sleep(delay)
        return False

    async def verify_active_session(self) -> bool:
        """
        Confirm the browser session is authenticated by visiting the user dashboard.

        Naukri redirects unauthenticated users to the login page from mnjuser URLs.
        """
        page = self._engine.page
        try:
            await page.goto(NAUKRI_DASHBOARD_URL, wait_until="domcontentloaded", timeout=45_000)
            await self._interactions.wait_for_navigation_complete()
            await asyncio.sleep(2)

            current_url = page.url.lower()
            if "nlogin" in current_url or current_url.rstrip("/").endswith("/login"):
                logger.debug("Dashboard navigation redirected to login — session inactive")
                return False
            if "mnjuser" in current_url:
                logger.debug("Dashboard accessible — session active")
                return True

            return await self.wait_and_check_logged_in()
        except Exception as e:
            logger.debug(f"Session verification via dashboard failed: {e}")
            return False

    async def is_logged_in(self) -> bool:
        """
        Check if the user is currently logged in by checking
        for profile indicators on the page.
        """
        page = self._engine.page

        # Explicitly check for Login buttons which mean NOT logged in
        try:
            not_logged_in = await page.query_selector(LoginSelectors.NOT_LOGGED_IN_INDICATORS)
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

    async def fill_credentials(self, email: str, password: str) -> None:
        """Fill in email and password fields."""
        await self._interactions.human_type(LoginSelectors.EMAIL_INPUT, email)
        await self._interactions.action_delay()
        await self._interactions.human_type(LoginSelectors.PASSWORD_INPUT, password)
        await self._interactions.action_delay()

    async def submit_password_login(self) -> None:
        """Press enter in password field and click the login button."""
        page = self._engine.page
        await page.keyboard.press("Enter")
        await self._interactions.safe_click(LoginSelectors.LOGIN_BUTTON, force=True)
        await asyncio.sleep(3)

    async def switch_to_otp_login(self) -> None:
        """Click the 'Use OTP to Login' link."""
        await self._interactions.safe_click(LoginSelectors.USE_OTP_LOGIN_LINK, force=True)
        await asyncio.sleep(2)

    async def fill_mobile_number(self, mobile_number: str) -> None:
        """Fill mobile number input."""
        await self._interactions.human_type(LoginSelectors.MOBILE_INPUT, mobile_number)
        await self._interactions.action_delay()

    async def click_get_otp(self) -> None:
        """Click 'Get OTP' button."""
        await self._interactions.safe_click(LoginSelectors.GET_OTP_BUTTON, force=True)
        await asyncio.sleep(3)

    async def detect_otp_input(self) -> bool:
        """Check if OTP input field is visible on the page."""
        page = self._engine.page
        otp_field = await page.query_selector(LoginSelectors.OTP_INPUT)
        if not otp_field:
            await asyncio.sleep(2)
            otp_field = await page.query_selector(LoginSelectors.OTP_INPUT)
        return bool(otp_field)

    async def fill_otp(self, otp: str) -> None:
        """Fill OTP input field."""
        await self._interactions.human_type(LoginSelectors.OTP_INPUT, otp)
        await self._interactions.action_delay()

    async def submit_otp(self) -> None:
        """Click OTP submit button."""
        await self._interactions.safe_click(LoginSelectors.OTP_SUBMIT, force=True)
        await asyncio.sleep(5)

    async def get_login_error_text(self) -> str:
        """Retrieve any error text visible on the login form."""
        return await self._interactions.get_text_content(LoginSelectors.LOGIN_ERROR)

    async def wait_for_otp_success(self, timeout: int) -> bool:
        """Wait for navigation or OTP input to disappear, indicating successful login."""
        page = self._engine.page
        try:
            await page.wait_for_url(
                f"{NAUKRI_BASE_URL}/**",
                timeout=timeout,
            )
            return True
        except Exception:
            # Alternative: wait for OTP field to disappear
            for _ in range(24):  # 24 * 5s = 120s
                await asyncio.sleep(5)
                otp_still_visible = await page.query_selector(LoginSelectors.OTP_INPUT)
                if not otp_still_visible:
                    return True
            return False
