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
        """Find the genuinely rendered login field and return a unique CSS selector.

        LinkedIn renders the sign-in form as a React component with generated ids
        (``_R_77vvcj...``) and keeps a hidden duplicate of every input mounted
        behind it. Playwright's ``:visible`` accepts those duplicates when they
        are only faded out, so visibility is computed strictly here and the
        element is then paired with its password counterpart.
        """
        js_code = r"""(inputType) => {
            const isRendered = (el) => {
                if (!el || el.offsetParent === null) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width <= 1 || rect.height <= 1) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility !== 'visible') return false;
                if (parseFloat(style.opacity || '1') < 0.05) return false;
                if (rect.bottom <= 0 || rect.right <= 0) return false;
                if (rect.top >= window.innerHeight || rect.left >= window.innerWidth) return false;
                return true;
            };
            const all = Array.from(document.querySelectorAll('input')).filter(isRendered);
            const passwords = all.filter(el => el.type === 'password');
            const identifier = all.filter(el =>
                el.type !== 'password' && el.type !== 'hidden' && el.type !== 'submit'
                && el.type !== 'checkbox' && el.type !== 'radio' && el.type !== 'file'
            );

            let pool;
            if (inputType === 'password') {
                pool = passwords;
            } else {
                const isSearch = (el) => {
                    const attrs = [el.name, el.id, el.getAttribute('aria-label'),
                                   el.placeholder, el.autocomplete, el.className]
                        .filter(Boolean).join(' ').toLowerCase();
                    return attrs.includes('search') || attrs.includes('nav');
                };
                const usable = identifier.filter(el => !isSearch(el));
                // Prefer inputs whose companion password field is also rendered,
                // which identifies the active form when duplicates are mounted.
                const paired = usable.filter(el => passwords.some(pw => {
                    const container = el.closest('form, div, section');
                    return container && container.contains(pw);
                }));
                const named = usable.filter(el => {
                    const attrs = [el.name, el.id, el.getAttribute('aria-label'),
                                   el.placeholder, el.autocomplete].join(' ').toLowerCase();
                    return attrs.includes('email') || attrs.includes('user')
                        || attrs.includes('login') || attrs.includes('session');
                });
                if (named.length > 0) pool = named;
                else if (paired.length > 0) pool = paired;
                else pool = usable.length > 0 ? usable : identifier;
            }

            if (pool.length === 0) return null;
            // When several render, the last one is the foreground (active) copy.
            const el = pool[pool.length - 1];
            if (el.id) return '#' + CSS.escape(el.id);
            if (el.name) return 'input[name="' + CSS.escape(el.name) + '"]';
            if (inputType === 'password') return 'input[type="password"]';
            return 'input[type="email"]';
        }"""
        try:
            return await page.evaluate(js_code, input_type)
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

    @staticmethod
    def _mask(value: str) -> str:
        """Mask a secret for logging while keeping it recognisable."""
        if not value:
            return "<empty>"
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"

    @staticmethod
    def _matches(actual: str, expected: str) -> bool:
        """Compare a field value against what we tried to enter.

        LinkedIn trims/rewrites some fields client-side, so an exact string
        compare rejects correct fills. Case-insensitive for identifiers like
        email, exact for secrets like passwords.
        """
        if actual is None:
            return False
        if expected == "":
            return actual == ""
        return actual.strip().casefold() == expected.strip().casefold()

    async def _fill_into(self, page, selector: str, value: str, *, identifier: bool) -> str | None:
        """Fill ``value`` into the element matched by ``selector``.

        Returns the selector when the element was found, filled and its value
        actually matches afterwards, otherwise ``None``.
        """
        try:
            loc = page.locator(selector).first
            if not await loc.is_visible(timeout=2000):
                return None
            await loc.click(force=True)
            await asyncio.sleep(0.3)
            await loc.fill("")
            await loc.fill(value)
            await asyncio.sleep(0.5)
            actual = await loc.input_value()
            if self._matches(actual, value):
                return selector
            logger.warning(
                f"{identifier} filled via '{selector}' but value did not match "
                f"(got {self._mask(actual)}, expected {self._mask(value)}) - wrong element, trying next"
            )
        except Exception as exc:
            logger.debug(f"Selector '{selector}' failed for {identifier}: {exc}")
        return None

    async def _verify_field(self, page, value: str, *, identifier: bool, selector: str | None = None) -> bool:
        """Re-read the live field and confirm it holds ``value``.

        ``selector`` is the one that worked during the fill; without it the
        field is rediscovered, which fails on LinkedIn's generated ids.
        """
        candidates: list[str] = []
        if selector:
            candidates.append(selector)
        if identifier:
            js_selector = await self._find_input_by_js(page, "email")
        else:
            js_selector = await self._find_input_by_js(page, "password")
        if js_selector and js_selector not in candidates:
            candidates.append(js_selector)

        for candidate in candidates:
            try:
                loc = page.locator(candidate).first
                if not await loc.is_visible(timeout=1500):
                    continue
                return self._matches(await loc.input_value(), value)
            except Exception:
                continue
        return False

    async def _fill_field(self, page, value: str, *, identifier: bool) -> str | None:
        """Populate one login field, returning the selector that worked.

        Strategies run cheapest-first: hardcoded selectors, then strict
        visibility detection (LinkedIn's React ids defeat hardcoded ones), then
        a native value injection as a last resort.
        """
        static = LoginSelectors.EMAIL_INPUT if identifier else LoginSelectors.PASSWORD_INPUT
        label = "Email" if identifier else "Password"

        # Detection runs first: LinkedIn serves generated ids and mounts a hidden
        # duplicate of every input, so a bare type selector can hit the copy that
        # is never submitted.
        js_selector = await self._find_input_by_js(page, "email" if identifier else "password")
        if js_selector:
            used = await self._fill_into(page, js_selector, value, identifier=identifier)
            if used:
                logger.info(f"{label} filled via rendered-field detection: {used}")
                return used

        for selector in static:
            used = await self._fill_into(page, selector, value, identifier=identifier)
            if used:
                logger.info(f"{label} filled via selector: {used}")
                return used

        if await self._inject_value(page, value, identifier=identifier) and await self._verify_field(
            page, value, identifier=identifier, selector=js_selector
        ):
            logger.info(f"{label} filled via JS value injection")
            return js_selector or ""

        return None

    async def _inject_value(self, page, value: str, *, identifier: bool) -> bool:
        """Last resort: write the value straight into the rendered field.

        React tracks the last value it rendered, so a bare ``value`` assignment
        is discarded. Resetting the tracker before dispatching ``input`` makes
        the controlled component accept it.
        """
        kind = "password" if not identifier else "identifier"
        js_code = """([value, kind]) => {
            const isRendered = (el) => {
                if (!el || el.offsetParent === null) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width <= 1 || rect.height <= 1) return false;
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility === 'visible'
                    && parseFloat(style.opacity || '1') >= 0.05;
            };
            const targets = Array.from(document.querySelectorAll('input')).filter(el => {
                if (!isRendered(el)) return false;
                if (kind === 'password') return el.type === 'password';
                return el.type === 'email' || (el.type === 'text' && !el.disabled);
            });
            if (targets.length === 0) return false;
            const el = targets[targets.length - 1];
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(el, '');
            if (el._valueTracker) el._valueTracker.setValue('');
            setter.call(el, value);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
            return true;
        }"""
        try:
            return bool(await page.evaluate(js_code, [value, kind]))
        except Exception as exc:
            logger.debug(f"{'Email' if identifier else 'Password'} JS injection failed: {exc}")
            return False

    async def fill_credentials(self, email: str, password: str) -> None:
        """Fill in email and password fields with multiple fallback strategies."""
        page = self._engine.page

        email = (email or "").strip()
        password = password or ""

        # Wait for page to be ready
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        await asyncio.sleep(3)

        email_selector = await self._fill_field(page, email, identifier=True)
        if not email_selector:
            await self._dump_page_inputs(page)
            raise RuntimeError("Could not find or fill email field on LinkedIn login page")

        await self._interactions.action_delay()

        password_selector = await self._fill_field(page, password, identifier=False)
        if not password_selector:
            await self._dump_page_inputs(page)
            raise RuntimeError("Could not find or fill password field on LinkedIn login page")

        if not await self._verify_field(page, email, identifier=True, selector=email_selector):
            await self._dump_page_inputs(page)
            raise RuntimeError(
                "Email field no longer holds the configured address before submit - "
                "LinkedIn would reject the form as 'invalid email'"
            )

        logger.info(f"Credentials staged for {self._mask(email)} - submitting")
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
