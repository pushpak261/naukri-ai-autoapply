"""
LoginPage Page Object for Naukri.com.
Encapsulates all selectors and page-level interactions for the login page.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.config.constants import (
    NAUKRI_BASE_URL,
    NAUKRI_LOGIN_URL,
    LoginSelectors,
)
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)

# Known Naukri error message texts that indicate login failure
_LOGIN_FAILURE_TEXTS = [
    "Invalid Email ID",
    "Invalid Password",
    "Invalid User",
    "Invalid Email ID - Password combination",
    "Incorrect password",
    "Incorrect email",
    "Incorrect username",
    "Account not found",
    "Authentication failed",
    "Please enter a valid",
    "does not exist",
    "is not registered",
    "Mobile number not",
    "OTP is invalid",
    "Wrong OTP",
    "captcha",
    "CAPTCHA",
]


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

        try:
            email_el = await page.query_selector(LoginSelectors.EMAIL_INPUT)
            if not email_el or not await email_el.is_visible():
                login_btn = await page.query_selector('a#login_Layer, a:has-text("Login"), button:has-text("Login")')
                if login_btn and await login_btn.is_visible():
                    await login_btn.click()
                    await asyncio.sleep(2)
        except Exception:
            pass

    async def navigate_to_base(self) -> None:
        """Navigate to Naukri base URL to check session."""
        page = self._engine.page
        await page.goto(NAUKRI_BASE_URL, wait_until="domcontentloaded")
        await self._interactions.wait_for_navigation_complete()
        await asyncio.sleep(2)

    async def wait_for_navigation_settle(self) -> None:
        """Wait for page to reach a settled state (post-login redirects, etc.)."""
        page = self._engine.page
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await asyncio.sleep(3)

    async def is_logged_in(self) -> bool:
        """
        Quick check if the user appears logged in by looking for
        profile indicators. Used during session validation.
        """
        page = self._engine.page

        # If we still see the login button, we're NOT logged in
        try:
            not_logged_in = await page.query_selector(LoginSelectors.NOT_LOGGED_IN_INDICATORS)
            if not_logged_in and await not_logged_in.is_visible():
                return False
        except PlaywrightError:
            pass

        # Check for logged-in profile indicators
        for selector in LoginSelectors.LOGGED_IN_INDICATORS:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    logger.debug(f"Login confirmed via selector: {selector}")
                    return True
            except PlaywrightError:
                continue

        # Check URL — if still on login path, not logged in
        current_url = page.url.lower()
        if "nlogin" in current_url or "login" in current_url.split("?")[0]:
            return False

        # Fallback: scan body text for "logout" or "my account" links
        try:
            text = await page.evaluate("document.body.innerText")
            lower = text.lower()
            if "logout" in lower or "my account" in lower or "my naukri" in lower:
                return True
        except PlaywrightError:
            pass

        return False

    async def verify_auth_state(self) -> tuple[bool, str]:
        """
        Deep authentication verification after a login attempt.

        Returns:
            (True, "") if fully authenticated.
            (False, reason_string) if not authenticated, with a description of why.
        """
        page = self._engine.page

        # Wait briefly for any post-login redirects to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # 1. URL check — must NOT be on the login page
        current_url = page.url.lower()
        if "nlogin" in current_url or current_url.rstrip("/").endswith("/login"):
            return False, "Still on login page"

        # 2. Login button must NOT be visible
        try:
            login_btn = await page.query_selector(LoginSelectors.NOT_LOGGED_IN_INDICATORS)
            if login_btn and await login_btn.is_visible():
                return False, "Login button is still visible"
        except PlaywrightError:
            pass

        # 3. Profile icon or user menu must be visible
        found_any_profile = False
        for selector in LoginSelectors.LOGGED_IN_INDICATORS:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    found_any_profile = True
                    break
            except PlaywrightError:
                continue
        if not found_any_profile:
            return False, "No profile indicator found on page"

        # 4. Check for error message elements (should not be present if logged in)
        error_text = await self._get_any_error_text()
        if error_text:
            return False, f"Error message present: {error_text}"

        # 5. Body text soft check (warning only — not a hard failure)
        try:
            text = await page.evaluate("document.body.innerText")
            lower = text.lower()
            has_logout = "logout" in lower
            has_my_naukri = "my naukri" in lower or "my account" in lower or "my profile" in lower
            if not (has_logout or has_my_naukri):
                logger.debug("Body text check: no logged-in keywords found (non-blocking)")
        except PlaywrightError:
            pass

        return True, ""

    async def get_login_error_text(self) -> str:
        """
        Retrieve any error text visible on the login form.
        Returns empty string if no error is detected.
        """
        text = await self._get_any_error_text()

        # Also check body text for known failure phrases
        if not text:
            try:
                body_text = await self._engine.page.evaluate("document.body.innerText")
                for phrase in _LOGIN_FAILURE_TEXTS:
                    if phrase.lower() in body_text.lower():
                        # Extract the sentence containing the error
                        for line in body_text.split("\n"):
                            if phrase.lower() in line.lower():
                                text = line.strip()[:200]
                                break
                        if not text:
                            text = phrase
                        break
            except PlaywrightError:
                pass

        return text

    async def _get_any_error_text(self) -> str:
        """Check all known error selectors and return the first text found."""
        page = self._engine.page
        error_selectors = [
            LoginSelectors.LOGIN_ERROR,
            "span.err",
            "span.error",
            "div.error",
            "#loginErrorMessage",
            ".loginError",
            ".formError",
            '[class*="errorMessage"]',
            '[class*="errMsg"]',
        ]
        for selector in error_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip()
                        if text:
                            return text
            except PlaywrightError:
                continue
        return ""

    async def is_on_login_page(self) -> bool:
        """Check if the browser is currently on the Naukri login page."""
        page = self._engine.page
        try:
            current_url = page.url.lower()
            if "nlogin" in current_url or current_url.rstrip("/").endswith("/login"):
                return True
            login_btn = await page.query_selector(LoginSelectors.NOT_LOGGED_IN_INDICATORS)
            if login_btn and await login_btn.is_visible():
                return True
        except PlaywrightError:
            pass
        return False

    async def has_captcha(self) -> bool:
        """Detect if a CAPTCHA challenge is present on the page."""
        page = self._engine.page
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="captcha"]',
            'div[class*="recaptcha"]',
            'div[class*="captcha"]',
            'iframe[title*="captcha" i]',
            'iframe[title*="recaptcha" i]',
        ]
        for selector in captcha_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except PlaywrightError:
                continue
        return False

    async def has_otp_pending(self) -> bool:
        """Check if OTP input is still visible (verification pending)."""
        try:
            return await self.detect_otp_input()
        except Exception:
            return False

    async def fill_credentials(self, email: str, password: str) -> None:
        """Fill in email and password fields."""
        page = self._engine.page
        try:
            email_el = await page.query_selector(LoginSelectors.EMAIL_INPUT)
            if not email_el or not await email_el.is_visible():
                login_btn = await page.query_selector('a#login_Layer, a:has-text("Login"), button:has-text("Login")')
                if login_btn and await login_btn.is_visible():
                    await login_btn.click()
                    await asyncio.sleep(2)
        except Exception:
            pass

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

    async def wait_for_otp_success(self, timeout: int) -> bool:
        """Wait for navigation or OTP input to disappear, indicating successful login."""
        page = self._engine.page
        try:
            await page.wait_for_url(
                f"{NAUKRI_BASE_URL}/**",
                timeout=timeout,
            )
            return True
        except PlaywrightTimeoutError:
            for _ in range(24):
                await asyncio.sleep(5)
                otp_still_visible = await page.query_selector(LoginSelectors.OTP_INPUT)
                if not otp_still_visible:
                    return True
            return False
