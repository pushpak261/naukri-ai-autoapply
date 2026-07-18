"""
LoginPage Page Object for LinkedIn.
Encapsulates all selectors and page-level interactions for the login page.
LinkedIn login is more complex than Naukri — includes 2FA, CAPTCHA challenges,
and security verification flows.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError

from src.linked_agent.browser.pages.base import BasePage
from src.linked_agent.config.constants import (
    LINKEDIN_BASE_URL,
    LINKEDIN_LOGIN_URL,
    LoginSelectors,
)
from src.linked_agent.utils.logger import get_logger
import contextlib

logger = get_logger(__name__)

_LOGIN_FAILURE_TEXTS = [
    "Wrong email or password",
    "Invalid credentials",
    "Please enter a valid email",
    "Enter a valid email or phone number",
    "That email",
    "We couldn't find an account",
    "Incorrect password",
    "authentication failed",
    "security verification",
    "captcha",
    "CAPTCHA",
    "unusual activity",
    "temporarily restricted",
]


class LinkedInLoginPage(BasePage):
    """Page Object representing the LinkedIn Login page."""

    async def navigate(self) -> None:
        """Navigate directly to the LinkedIn login page."""
        page = self._engine.page
        await page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded")
        await self._interactions.wait_for_navigation_complete()
        await asyncio.sleep(2)

    async def navigate_to_base(self) -> None:
        """Navigate to LinkedIn base URL to check session."""
        page = self._engine.page
        await page.goto(LINKEDIN_BASE_URL, wait_until="domcontentloaded")
        await self._interactions.wait_for_navigation_complete()
        await asyncio.sleep(2)

    async def wait_for_navigation_settle(self) -> None:
        """Wait for page to reach a settled state (post-login redirects, etc.)."""
        page = self._engine.page
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=15_000)
        await asyncio.sleep(3)

    async def is_logged_in(self) -> bool:
        """Quick check if the user appears logged in."""
        page = self._engine.page

        # Check if we see login/signup buttons — if so, NOT logged in
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
                    logger.debug(f"LinkedIn login confirmed via selector: {selector}")
                    return True
            except PlaywrightError:
                continue

        # Check URL
        current_url = page.url.lower()
        if "/login" in current_url or "/checkpoint" in current_url or "/signup" in current_url:
            return False

        # Fallback: scan body text
        try:
            text = await page.evaluate("document.body.innerText")
            lower = text.lower()
            if "sign out" in lower or "my network" in lower or "feed" in lower:
                return True
        except PlaywrightError:
            pass

        return False

    async def verify_auth_state(self) -> tuple[bool, str]:
        """
        Deep authentication verification after a login attempt.
        Returns (True, "") if fully authenticated, (False, reason) otherwise.
        """
        page = self._engine.page

        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=15_000)
        await asyncio.sleep(2)

        # 1. URL check
        current_url = page.url.lower()
        if "/login" in current_url or "/checkpoint" in current_url:
            return False, "Still on login page or checkpoint"

        # 2. Login button must NOT be visible
        try:
            login_btn = await page.query_selector(LoginSelectors.NOT_LOGGED_IN_INDICATORS)
            if login_btn and await login_btn.is_visible():
                return False, "Login button is still visible"
        except PlaywrightError:
            pass

        # 3. Profile indicator check
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

        # 4. Error message check
        error_text = await self.get_login_error_text()
        if error_text:
            return False, f"Error message present: {error_text}"

        return True, ""

    async def get_login_error_text(self) -> str:
        """Retrieve any error text visible on the login form."""
        text = await self._get_any_error_text()

        if not text:
            try:
                body_text = await self._engine.page.evaluate("document.body.innerText")
                for phrase in _LOGIN_FAILURE_TEXTS:
                    if phrase.lower() in body_text.lower():
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
            'div[role="alert"]',
            'p[class*="form__error"]',
            "#session_key-error",
            "#session_password-error",
            ".login-form__error",
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
        """Check if the browser is currently on the LinkedIn login page."""
        page = self._engine.page
        try:
            current_url = page.url.lower()
            if "/login" in current_url or "/checkpoint" in current_url:
                return True
            login_btn = await page.query_selector(LoginSelectors.NOT_LOGGED_IN_INDICATORS)
            if login_btn and await login_btn.is_visible():
                return True
        except PlaywrightError:
            pass
        return False

    async def has_captcha(self) -> bool:
        """Detect if a CAPTCHA challenge is present."""
        page = self._engine.page
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="captcha"]',
            'div[class*="recaptcha"]',
            'div[class*="captcha"]',
            'iframe[title*="captcha" i]',
            "div[data-hcaptcha-widget-id]",
            "#captcha-internal",
        ]
        for selector in captcha_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except PlaywrightError:
                continue
        return False

    async def _find_input_by_js(self, page, input_type: str) -> str | None:
        """Use JavaScript to find an input element by type/attributes. Returns a unique CSS selector."""
        js_code = """(inputType) => {
            const inputs = Array.from(document.querySelectorAll('input'));
            // Filter to visible, non-hidden inputs
            const visible = inputs.filter(el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && el.offsetParent !== null;
            });
            if (inputType === 'email') {
                // Look for text/email/tel inputs that aren't password
                const candidates = visible.filter(el =>
                    el.type !== 'password' && el.type !== 'hidden' && el.type !== 'submit'
                    && el.type !== 'checkbox' && el.type !== 'radio'
                );
                // Prefer by name/aria-label/placeholder containing email/user/login
                const preferred = candidates.filter(el => {
                    const attrs = [el.name, el.id, el.getAttribute('aria-label'), el.placeholder, el.autocomplete].join(' ').toLowerCase();
                    return attrs.includes('email') || attrs.includes('user') || attrs.includes('login') || attrs.includes('phone') || attrs.includes('session');
                });
                const pool = preferred.length > 0 ? preferred : candidates;
                if (pool.length === 0) return null;
                const el = pool[0];
                // Build a selector
                if (el.id) return '#' + CSS.escape(el.id);
                if (el.name) return 'input[name="' + CSS.escape(el.name) + '"]';
                if (el.getAttribute('aria-label')) return 'input[aria-label="' + CSS.escape(el.getAttribute('aria-label')) + '"]';
                // Use nth
                const idx = visible.indexOf(el);
                return 'input:visible >> nth=' + idx;
            } else {
                // password
                const pwds = visible.filter(el => el.type === 'password');
                if (pwds.length === 0) return null;
                const el = pwds[0];
                if (el.id) return '#' + CSS.escape(el.id);
                if (el.name) return 'input[name="' + CSS.escape(el.name) + '"]';
                return 'input[type="password"]';
            }
        }"""
        try:
            result = await page.evaluate(js_code, input_type)
            return result
        except Exception:
            return None

    async def _dump_page_inputs(self, page) -> None:
        """Diagnostic: log all visible input elements on the page."""
        try:
            js_code = """() => {
                const inputs = Array.from(document.querySelectorAll('input'));
                return inputs.map(el => ({
                    tag: el.tagName,
                    type: el.type,
                    id: el.id,
                    name: el.name,
                    ariaLabel: el.getAttribute('aria-label'),
                    placeholder: el.placeholder,
                    className: el.className.substring(0, 80),
                    visible: el.offsetParent !== null,
                }));
            }"""
            inputs = await page.evaluate(js_code)
            if inputs:
                logger.info(f"Page has {len(inputs)} input elements:")
                for inp in inputs:
                    logger.info(
                        f"  input type={inp.get('type','')} id={inp.get('id','')} "
                        f"name={inp.get('name','')} aria-label={inp.get('ariaLabel','')} "
                        f"placeholder={inp.get('placeholder','')} visible={inp.get('visible','')}"
                    )
            else:
                logger.info("No input elements found on page")
        except Exception as e:
            logger.debug(f"Could not dump page inputs: {e}")

    async def fill_credentials(self, email: str, password: str) -> None:
        """Fill in email and password fields with multiple fallback strategies."""
        page = self._engine.page

        # Wait for page to be ready
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        await asyncio.sleep(3)

        # --- Email ---
        email_filled = False
        # Strategy 1: Try CSS selectors
        for selector in LoginSelectors.EMAIL_INPUT.split(","):
            selector = selector.strip()
            try:
                loc = page.locator(selector).first
                if await loc.is_visible(timeout=2000):
                    await loc.click(force=True)
                    await asyncio.sleep(0.3)
                    await loc.fill("")
                    await loc.fill(email)
                    await asyncio.sleep(0.5)
                    val = await loc.input_value()
                    if val == email:
                        email_filled = True
                        logger.info(f"Email filled via selector: {selector}")
                        break
            except Exception:
                continue

        # Strategy 2: JavaScript-based detection
        if not email_filled:
            js_selector = await self._find_input_by_js(page, "email")
            if js_selector:
                try:
                    loc = page.locator(js_selector).first
                    if await loc.is_visible(timeout=3000):
                        await loc.click(force=True)
                        await asyncio.sleep(0.3)
                        await loc.fill(email)
                        await asyncio.sleep(0.5)
                        val = await loc.input_value()
                        if val == email:
                            email_filled = True
                            logger.info(f"Email filled via JS selector: {js_selector}")
                except Exception:
                    pass

        # Strategy 3: Direct JS value injection
        if not email_filled:
            try:
                await page.evaluate(
                    """(email) => {
                    const inputs = Array.from(document.querySelectorAll('input'));
                    for (const el of inputs) {
                        if (el.type !== 'password' && el.type !== 'hidden' && el.type !== 'submit'
                            && el.type !== 'checkbox' && el.type !== 'radio'
                            && el.offsetParent !== null) {
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            ).set;
                            nativeInputValueSetter.call(el, email);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                    }
                    return false;
                }""",
                    email,
                )
                email_filled = True
                logger.info("Email filled via JS value injection")
            except Exception:
                pass

        if not email_filled:
            await self._dump_page_inputs(page)
            raise RuntimeError("Could not find or fill email field on LinkedIn login page")

        await self._interactions.action_delay()

        # --- Password ---
        password_filled = False
        # Strategy 1: CSS selectors
        for selector in LoginSelectors.PASSWORD_INPUT.split(","):
            selector = selector.strip()
            try:
                loc = page.locator(selector).first
                if await loc.is_visible(timeout=2000):
                    await loc.click(force=True)
                    await asyncio.sleep(0.3)
                    await loc.fill("")
                    await loc.fill(password)
                    await asyncio.sleep(0.5)
                    val = await loc.input_value()
                    if val == password:
                        password_filled = True
                        logger.info(f"Password filled via selector: {selector}")
                        break
            except Exception:
                continue

        # Strategy 2: JS detection
        if not password_filled:
            js_selector = await self._find_input_by_js(page, "password")
            if js_selector:
                try:
                    loc = page.locator(js_selector).first
                    if await loc.is_visible(timeout=3000):
                        await loc.click(force=True)
                        await asyncio.sleep(0.3)
                        await loc.fill(password)
                        await asyncio.sleep(0.5)
                        val = await loc.input_value()
                        if val == password:
                            password_filled = True
                            logger.info(f"Password filled via JS selector: {js_selector}")
                except Exception:
                    pass

        # Strategy 3: Direct JS injection
        if not password_filled:
            try:
                await page.evaluate(
                    """(password) => {
                    const el = document.querySelector('input[type="password"]');
                    if (el && el.offsetParent !== null) {
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        nativeInputValueSetter.call(el, password);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }""",
                    password,
                )
                password_filled = True
                logger.info("Password filled via JS value injection")
            except Exception:
                pass

        if not password_filled:
            await self._dump_page_inputs(page)
            raise RuntimeError("Could not find or fill password field on LinkedIn login page")

        await self._interactions.action_delay()

    async def submit_login(self) -> None:
        """Click the sign-in button."""
        await self._interactions.safe_click(LoginSelectors.LOGIN_BUTTON, force=True)
        await asyncio.sleep(3)

    async def detect_2fa_input(self) -> bool:
        """Check if 2FA input field is visible."""
        page = self._engine.page
        try:
            otp_field = await page.query_selector(LoginSelectors.OTP_INPUT)
            if not otp_field:
                await asyncio.sleep(2)
                otp_field = await page.query_selector(LoginSelectors.OTP_INPUT)
            return bool(otp_field)
        except Exception:
            return False

    async def fill_2fa(self, code: str) -> None:
        """Fill 2FA code input."""
        await self._interactions.human_type(LoginSelectors.OTP_INPUT, code)
        await self._interactions.action_delay()

    async def submit_2fa(self) -> None:
        """Click 2FA submit button."""
        await self._interactions.safe_click(LoginSelectors.OTP_SUBMIT, force=True)
        await asyncio.sleep(5)
