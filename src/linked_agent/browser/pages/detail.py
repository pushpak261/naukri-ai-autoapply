"""
JobDetailPage Page Object for LinkedIn.
Handles job detail extraction and the Easy Apply flow.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.linked_agent.browser.pages.base import BasePage
from src.linked_agent.config.constants import JobDetailSelectors
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInJobDetailPage(BasePage):
    """Page Object representing a LinkedIn job detail page."""

    async def navigate_to_job(self, job_url: str, retries: int = 3) -> bool:
        """Navigate to a specific job detail page with retries."""
        page = self._engine.page
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
                await self._interactions.wait_for_navigation_complete()
                await asyncio.sleep(3)
                return True
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                last_error = e
                logger.warning(f"Detail navigation attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    await asyncio.sleep(2 * attempt)
        logger.error(f"Failed to navigate to job page after {retries} attempts: {job_url}: {last_error}")
        return False

    async def extract_job_details(self) -> dict[str, str]:
        """Extract full job details from the detail page."""
        page = self._engine.page
        details: dict[str, str] = {}

        # Try a quick wait for any content, then fall back to JS extraction
        loaded = False
        try:
            await page.wait_for_selector('h1, h2, div[class*="job"], section[class*="job"], div[class*="description"]', timeout=10000)
            loaded = True
        except PlaywrightTimeoutError:
            logger.warning("Job detail content did not load within timeout — attempting JS extraction anyway")

        # Multi-strategy JS extraction - tries modern, legacy, and text-based selectors
        js_script = """
        () => {
            const details = {};

            // -- Title --
            let titleText = '';
            // Strategy 0: page title (LinkedIn sets "<Job Title> | LinkedIn" format)
            const pageTitle = document.title || '';
            if (pageTitle && (!pageTitle.includes('LinkedIn') || pageTitle.includes('|'))) {
                const parts = pageTitle.split('|');
                if (parts.length >= 2) {
                    const candidate = parts[0].trim();
                    if (candidate.length > 3 && candidate.length < 200) {
                        titleText = candidate;
                    }
                }
            }
            // Strategy 1: try common h1/h2 selectors
            if (!titleText) {
                const titleSelectors = [
                    'h1[class*="job-title"]',
                    'h1[class*="top-card"]',
                    'h1.top-card-layout__title',
                    'h1.job-title',
                    'h1',
                    'h2[class*="job-title"]',
                    'h2',
                    'span[class*="job-title"]',
                ];
                for (const sel of titleSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.trim().length > 3) {
                        titleText = el.innerText.trim();
                        break;
                    }
                }
            }
            details.title = titleText;

            // -- Company --
            const compElem =
                document.querySelector('a[class*="company-name"]')
                || document.querySelector('.job-details-jobs-unified-top-card__company-name a')
                || document.querySelector('.job-details-jobs-unified-top-card__company-name')
                || document.querySelector('.top-card-layout__second-line a')
                || document.querySelector('[class*="company"] a');
            details.company = compElem ? compElem.innerText.trim() : '';

            // -- Description -- (multi-strategy, most critical field)
            let descText = '';
            // Strategy 1: Modern description containers
            const descSelectors = [
                '.jobs-description__content',
                '.jobs-box__html-content',
                '.show-more-less-html__markup',
                '.description__text',
                'div[class*="description__text"]',
                'section[aria-label*="description" i]',
                'div[class*="jobs-description"]',
                'div[class*="show-more"]',
            ];
            for (const sel of descSelectors) {
                const el = document.querySelector(sel);
                if (el && el.innerText && el.innerText.trim().length > 20) {
                    descText = el.innerText.trim();
                    break;
                }
            }
            // Strategy 2: Find the largest text block in the page (likely the description)
            if (!descText) {
                let maxLen = 0;
                let maxBlock = '';
                document.querySelectorAll('div, section, article').forEach(el => {
                    const text = el.innerText || '';
                    if (text.length > maxLen && text.length < 50000 && el.children.length > 2) {
                        // Skip nav/header/footer blocks
                        const tag = el.tagName.toLowerCase();
                        if (tag !== 'nav' && tag !== 'header' && tag !== 'footer' && !el.closest('nav') && !el.closest('header')) {
                            maxLen = text.length;
                            maxBlock = text.trim();
                        }
                    }
                });
                if (maxBlock.length > 50) descText = maxBlock;
            }
            details.description = descText;

            // -- Location --
            const locElem =
                document.querySelector('[class*="primary-description"] span')
                || document.querySelector('.job-details-jobs-unified-top-card__primary-description span')
                || document.querySelector('.top-card-layout__headline span')
                || document.querySelector('[class*="location"]');
            details.location = locElem ? locElem.innerText.trim() : '';

            // -- Skills / Insights --
            const insightElems = document.querySelectorAll(
                '[class*="job-insight"] span, [class*="insights"] span'
            );
            details.insights = Array.from(insightElems).map(e => e.innerText.trim()).filter(Boolean).join(' | ');

            // -- Salary (if present) --
            let salaryText = '';
            for (const el of insightElems) {
                const t = el.innerText || '';
                if (t.includes('$') || t.toLowerCase().includes('salary') || t.includes('/yr') || t.includes('/mo') || t.includes('/hr') || t.includes(String.fromCharCode(8377))) {
                    salaryText = t.trim();
                    break;
                }
            }
            details.salary = salaryText;

            // -- Easy Apply button -- (text-based is most resilient)
            let easyApply = false;
            // Check for explicit Easy Apply text on any button
            const allBtns = document.querySelectorAll('button');
            for (const btn of allBtns) {
                const btnText = (btn.innerText || '').toLowerCase();
                const btnLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                if (btnText.includes('easy apply') || btnLabel.includes('easy apply')) {
                    easyApply = true;
                    break;
                }
            }
            details.easy_apply = easyApply;

            // -- Already applied? --
            let alreadyApplied = false;
            for (const el of document.querySelectorAll('span, button, div')) {
                const t = (el.innerText || '').trim();
                if (t === 'Applied' || t.toLowerCase() === 'already applied') {
                    alreadyApplied = true;
                    break;
                }
            }
            details.already_applied = alreadyApplied;

            return details;
        }
        """

        try:
            raw_details = await page.evaluate(js_script)
            details = raw_details if isinstance(raw_details, dict) else {}
            desc_len = len(details.get("description", ""))
            logger.info(f"Detail extraction — title: '{details.get('title', '')[:50]}', desc: {desc_len} chars, easy_apply: {details.get('easy_apply')}")
        except PlaywrightError as e:
            logger.error(f"Failed to extract job details: {e}")

        return details

    async def has_easy_apply(self) -> bool:
        """Check if any Apply button is present that can open the Easy Apply modal.
        Detects both 'Easy Apply' buttons and regular 'Apply' buttons (LinkedIn
        often shows just 'Apply' but still opens the Easy Apply modal)."""
        page = self._engine.page
        try:
            # Wait up to 8s for the button to appear (LinkedIn React lazy-loads it)
            await page.wait_for_selector(
                JobDetailSelectors.APPLY_BUTTON, timeout=8000, state="visible"
            )
            return True
        except PlaywrightTimeoutError:
            pass

        # Debug: log what buttons ARE on the page
        try:
            debug = await page.evaluate("""() => {
                const btns = [];
                document.querySelectorAll('button').forEach(b => {
                    const t = (b.textContent || b.innerText || '').trim().substring(0, 80);
                    const a = b.getAttribute('aria-label') || '';
                    if ((t.toLowerCase().includes('apply') || a.toLowerCase().includes('apply'))
                        && !a.includes('filter') && !t.toLowerCase().includes('show results')) {
                        btns.push({text: t, aria: a, visible: b.offsetParent !== null, display: getComputedStyle(b).display});
                    }
                });
                return btns;
            }""")
            if debug:
                logger.warning(f"has_easy_apply timed out but found buttons: {debug}")
            else:
                logger.warning("has_easy_apply timed out — NO apply buttons on page at all")
        except Exception as e:
            logger.debug(f"Could not inspect buttons: {e}")

        # JS fallback: check for ANY apply button (Easy Apply or regular "Apply")
        try:
            fallback = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const tc = (b.textContent || b.innerText || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').toLowerCase();
                    const isApply = tc.includes('apply') || a.includes('apply');
                    const isFilter = a.includes('filter') || tc.includes('show results') || a.includes('show results');
                    if (isApply && !isFilter && b.offsetParent !== null && !b.disabled) {
                        return true;
                    }
                }
                return false;
            }""")
            if fallback:
                logger.warning("has_easy_apply resolved via JS fallback — Apply button IS present")
                return True
        except Exception as e:
            logger.debug(f"JS fallback check failed: {e}")

        return False

    async def has_already_applied(self) -> bool:
        """Check if already applied to this job (with brief wait)."""
        page = self._engine.page
        try:
            await page.wait_for_selector(
                JobDetailSelectors.ALREADY_APPLIED, timeout=3000, state="visible"
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def click_easy_apply(self) -> bool:
        """Click the Easy Apply button in the sidebar to open the application modal.
        Matches both 'Easy Apply' and regular 'Apply' buttons since both
        can open the same LinkedIn Easy Apply modal.

        Returns True if the button was found and clicked — the caller is
        responsible for waiting for the modal via wait_for_apply_modal().
        """
        page = self._engine.page

        # Strategy 1: Playwright's built-in selector (matches Easy Apply + Apply)
        try:
            btn = await page.query_selector(JobDetailSelectors.APPLY_BUTTON)
            if btn:
                try:
                    await btn.click(timeout=5000)
                    logger.info("Apply button clicked successfully via Playwright selector")
                    return True
                except PlaywrightError:
                    logger.debug("Playwright click failed, trying JS fallback")
        except Exception as e:
            logger.debug(f"Playwright selector failed: {e}")

        # Strategy 2: JS fallback — text-based matching, prioritizes Easy Apply
        # but also clicks regular "Apply" buttons that open the modal.
        try:
            clicked = await page.evaluate("""() => {
                const allBtns = document.querySelectorAll('button');

                // Helper: check if a button is an apply button
                function isApplyBtn(b) {
                    const tc = (b.textContent || b.innerText || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').toLowerCase();
                    return (tc.includes('apply') || a.includes('apply'))
                        && !a.includes('filter')
                        && !tc.includes('show results')
                        && !a.includes('show results');
                }

                // Helper: check if button is truly visible
                function isVisible(b) {
                    if (b.offsetParent === null) return false;
                    if (b.disabled) return false;
                    const style = window.getComputedStyle(b);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    return true;
                }

                // Try sidebar first (most specific)
                const sidebar = document.querySelector('.jobs-search__job-details, .job-details, [class*="job-details"], [class*="scaffold-layout__detail"]');
                if (sidebar) {
                    const btns = sidebar.querySelectorAll('button');
                    // Prioritize Easy Apply text
                    for (const b of btns) {
                        const tc = (b.textContent || b.innerText || '').trim().toLowerCase();
                        const a = (b.getAttribute('aria-label') || '').toLowerCase();
                        if ((tc.includes('easy apply') || a.includes('easy apply')) && isVisible(b)) {
                            b.click(); return true;
                        }
                    }
                    // Then try any Apply button
                    for (const b of btns) {
                        if (isApplyBtn(b) && isVisible(b)) { b.click(); return true; }
                    }
                }

                // Try all buttons on page — prioritize Easy Apply
                for (const b of allBtns) {
                    const tc = (b.textContent || b.innerText || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').toLowerCase();
                    if ((tc.includes('easy apply') || a.includes('easy apply')) && isVisible(b)) {
                        b.click(); return true;
                    }
                }
                for (const b of allBtns) {
                    if (isApplyBtn(b) && isVisible(b)) { b.click(); return true; }
                }

                return false;
            }""")
            if not clicked:
                logger.warning("No Apply button found to click (Easy Apply or regular Apply)")
                return False
        except Exception as e:
            logger.error(f"Failed to click Apply button: {e}")
            return False

        logger.info("Apply button clicked successfully (JS fallback)")
        return True

    async def has_external_apply(self) -> bool:
        """Check if an external Apply button/link is present (with brief wait)."""
        page = self._engine.page
        try:
            await page.wait_for_selector(
                JobDetailSelectors.EXTERNAL_APPLY, timeout=5000, state="visible"
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def click_any_apply_button(self) -> bool:
        """Click external/navigation Apply buttons (those that redirect to
        external career sites). Also catches any Apply button missed by
        click_easy_apply() — the caller will check for Easy Apply modal
        after clicking regardless."""
        page = self._engine.page
        try:
            result = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                function isVisible(b) {
                    if (b.offsetParent === null) return false;
                    if (b.disabled) return false;
                    const style = window.getComputedStyle(b);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    return true;
                }
                for (const b of btns) {
                    const tc = (b.textContent || b.innerText || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').toLowerCase();
                    // Prioritize "Apply on" / external apply indicators
                    if ((tc.includes('apply on') || a.includes('apply on')) && isVisible(b)) {
                        b.click(); return true;
                    }
                }
                for (const b of btns) {
                    const tc = (b.textContent || b.innerText || '').trim().toLowerCase();
                    const a = (b.getAttribute('aria-label') || '').toLowerCase();
                    if ((tc.includes('apply') || a.includes('apply'))
                        && !a.includes('filter')
                        && !tc.includes('show results')
                        && !a.includes('show results')
                        && isVisible(b)) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }
            """)
            if result:
                await asyncio.sleep(2)
                logger.info("Clicked Apply button (external fallback)")
            return result
        except Exception as e:
            logger.error(f"Failed to click any apply button: {e}")
            return False

    async def click_external_apply(self) -> str | None:
        """
        Click the external Apply button/link and capture the resulting URL.
        Returns the external URL if a new tab/page opens, otherwise None.
        """
        page = self._engine.page
        try:
            # Listen for new pages (LinkedIn opens external apply in new tab)
            new_page_url = None

            async def on_popup(popup):
                nonlocal new_page_url
                try:
                    await popup.wait_for_load_state("domcontentloaded", timeout=10000)
                    new_page_url = popup.url
                except Exception:
                    new_page_url = popup.url if popup.url else None

            page.context.on("page", on_popup)

            # Click the external apply button
            clicked = await self._interactions.safe_click(
                JobDetailSelectors.EXTERNAL_APPLY, force=True
            )
            if not clicked:
                return None

            # Wait a moment for new tab to open
            await asyncio.sleep(3)

            # Remove listener
            page.context.remove_listener("page", on_popup)

            if new_page_url and new_page_url != page.url:
                return new_page_url

            # If no new tab, check if current page navigated
            current_url = page.url
            if "apply" in current_url.lower() and current_url != page.url:
                return current_url

            # Try to extract external URL from any redirect link on the page
            js_extract = """
            () => {
                // Check for "Apply" links that point to external sites
                const links = document.querySelectorAll('a[href*="apply"], a[href*="career"], a[aria-label*="apply" i]');
                for (const link of links) {
                    const href = link.getAttribute('href') || '';
                    if (href && !href.includes('linkedin.com') && href.startsWith('http')) {
                        return href;
                    }
                }
                // Check for any external redirect URL in the page
                const redirectLink = document.querySelector('a[href*="redirect"], a[data-tracking-control-name*="apply"]');
                if (redirectLink) {
                    const href = redirectLink.getAttribute('href') || '';
                    if (href && href.startsWith('http')) return href;
                }
                return null;
            }
            """
            result = await page.evaluate(js_extract)
            if result:
                return result

            return None
        except Exception as e:
            logger.warning(f"Error clicking external apply: {e}")
            return None

    async def wait_for_apply_modal(self, timeout: int = 10000) -> bool:
        """Wait for the Easy Apply modal to appear."""
        page = self._engine.page
        # Try multiple modal selectors in sequence
        modal_selectors = [
            'div.jobs-easy-apply-modal',
            'div[role="dialog"]',
            'div.artdeco-modal',
            'div[class*="modal"]',
            'div[class*="overlay"]',
            'div[class*="apply"]',
            'form[aria-label*="Apply" i]',
            'section[aria-label*="Apply" i]',
        ]

        # First try the combined selector
        try:
            await page.wait_for_selector(
                JobDetailSelectors.EASY_APPLY_MODAL, timeout=min(timeout, 3000), state="visible"
            )
            logger.debug("Modal found via combined selector")
            return True
        except PlaywrightTimeoutError:
            pass

        # Try each selector individually
        for selector in modal_selectors:
            try:
                await page.wait_for_selector(selector, timeout=min(timeout // len(modal_selectors), 2000), state="visible")
                logger.debug(f"Modal found via selector: {selector}")
                return True
            except PlaywrightTimeoutError:
                continue

        # Fallback: check if any new large element appeared (modal might have different markup)
        try:
            new_element = await page.evaluate("""
                () => {
                    // Check for any dialog-like element that appeared
                    const dialogs = document.querySelectorAll('[role="dialog"], [role="alertdialog"], [role="modal"]');
                    for (const d of dialogs) {
                        if (d.offsetHeight > 100 && d.offsetWidth > 100) {
                            return {found: true, tag: d.tagName, role: d.getAttribute('role'), class: d.className};
                        }
                    }
                    // Check for any overlay/modal
                    const overlays = document.querySelectorAll('[class*="modal"], [class*="overlay"], [class*="popup"]');
                    for (const o of overlays) {
                        if (o.offsetHeight > 100 && o.offsetWidth > 100 && getComputedStyle(o).display !== 'none') {
                            return {found: true, tag: o.tagName, class: o.className};
                        }
                    }
                    return {found: false};
                }
            """)
            if new_element and new_element.get('found'):
                logger.debug(f"Modal found via fallback: {new_element}")
                return True
        except Exception as e:
            logger.debug(f"Fallback modal check failed: {e}")

        # Take debug screenshot
        try:
            await page.screenshot(path="debug_modal_not_found.png")
            logger.debug("Debug screenshot saved: debug_modal_not_found.png")
        except Exception:
            pass

        return False

    async def extract_screening_questions(self) -> list[dict[str, str]]:
        """
        Extract screening questions from the Easy Apply modal.
        LinkedIn uses a multi-step form; this extracts questions from the current step.
        """
        page = self._engine.page
        questions: list[dict[str, str]] = []

        js_script = """
        () => {
            const questions = [];
            const seen = new Set();
            const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
            if (!modal) return questions;

            // Find any file inputs — mark as file upload
            const fileInputs = modal.querySelectorAll('input[type="file"]');
            for (const fi of fileInputs) {
                const label = fi.closest('label') || fi.parentElement;
                const qText = label ? label.innerText.trim() : 'File upload';
                if (seen.has(qText)) continue;
                seen.add(qText);
                questions.push({
                    question: qText,
                    field_type: 'file',
                    options: [],
                    current_value: fi.files && fi.files.length > 0 ? fi.files[0].name : '',
                    is_required: fi.required
                });
            }

            // Strategy 1: find by form group containers
            const formGroups = modal.querySelectorAll('.jobs-easy-apply-form-section__grouping, .fb-dash-form-element');
            for (const group of formGroups) {
                const label = group.querySelector('label, .t-14');
                if (!label) continue;
                const questionText = label.innerText.trim();
                if (!questionText || seen.has(questionText)) continue;
                // Skip radio option labels that are just "Yes"/"No"/"Other"
                if (['yes', 'no', 'other', 'none'].includes(questionText.toLowerCase())) continue;
                if (questionText.toLowerCase().includes('deselect resume') || questionText.toLowerCase().includes('remove resume')) continue;
                seen.add(questionText);

                // Skip if this group contains a file input
                if (group.querySelector('input[type="file"]')) continue;

                const textInput = group.querySelector('input[type="text"], input[type="number"], textarea');
                const selectInput = group.querySelector('select, div[role="listbox"]');
                const radioInputs = group.querySelectorAll('input[type="radio"], div[role="radio"]');
                const checkboxInputs = group.querySelectorAll('input[type="checkbox"], div[role="checkbox"]');

                let field_type = 'text';
                let options = [];
                let current_value = '';

                if (radioInputs.length > 0) {
                    field_type = 'radio';
                    options = Array.from(radioInputs).map(r => {
                        const rl = r.closest('label') || r.parentElement;
                        return rl ? rl.innerText.trim() : '';
                    }).filter(Boolean);
                } else if (checkboxInputs.length > 0) {
                    field_type = 'checkbox';
                    options = Array.from(checkboxInputs).map(c => {
                        const cl = c.closest('label') || c.parentElement;
                        return cl ? cl.innerText.trim() : '';
                    }).filter(Boolean);
                } else if (selectInput) {
                    field_type = 'dropdown';
                    if (selectInput.tagName === 'SELECT') {
                        options = Array.from(selectInput.options).map(o => o.text.trim()).filter(Boolean);
                        current_value = selectInput.value || '';
                    } else if (selectInput.getAttribute('role') === 'listbox') {
                        const items = selectInput.querySelectorAll('[role="option"]');
                        options = Array.from(items).map(o => (o.innerText || o.getAttribute('aria-label') || '').trim()).filter(Boolean);
                        const selected = selectInput.querySelector('[role="option"][aria-selected="true"]');
                        current_value = selected ? (selected.innerText || selected.getAttribute('aria-label') || '').trim() : '';
                    }
                } else if (textInput) {
                    current_value = textInput.value || '';
                }

                questions.push({
                    question: questionText,
                    field_type: field_type,
                    options: options,
                    current_value: current_value,
                    is_required: label.getAttribute('aria-required') === 'true' ||
                                 group.querySelector('[aria-required="true"]') !== null
                });
            }

            // Strategy 2: find labels with associated inputs not caught by Strategy 1
            const allLabels = modal.querySelectorAll('label');
            for (const label of allLabels) {
                const questionText = label.innerText.trim();
                if (!questionText || seen.has(questionText)) continue;
                // Skip labels that are just "Yes"/"No"/"Other" — these are radio options, not questions
                if (['yes', 'no', 'other', 'none'].includes(questionText.toLowerCase())) continue;
                // Skip "Deselect resume" / "Select resume" labels — these are resume management controls
                if (questionText.toLowerCase().includes('deselect resume') || questionText.toLowerCase().includes('remove resume') || questionText.toLowerCase().includes('select resume')) continue;
                seen.add(questionText);

                const forId = label.getAttribute('for');
                let input = forId ? document.getElementById(forId) : label.querySelector('input, select, textarea');
                if (!input) input = label.closest('.fb-dash-form-element, .artdeco-entity-lockup, div')?.querySelector('input, select, textarea');
                if (!input) continue;

                // Skip file inputs (already handled above)
                if (input.type === 'file') continue;

                let field_type = 'text';
                let options = [];
                let current_value = '';

                if (input.tagName === 'SELECT') {
                    field_type = 'dropdown';
                    options = Array.from(input.options).map(o => o.text.trim()).filter(Boolean);
                    current_value = input.value || '';
                } else if (input.type === 'radio') {
                    field_type = 'radio';
                    // Find the fieldset or container with a heading for this radio group
                    const fieldset = input.closest('fieldset');
                    if (fieldset) {
                        const legend = fieldset.querySelector('legend');
                        if (legend && !seen.has(legend.innerText.trim())) {
                            // Use legend as question text
                            const legendText = legend.innerText.trim();
                            seen.add(legendText);
                            if (questions.length > 0 && questions[questions.length - 1].question === questionText) {
                                questions.pop();
                            }
                            questions.push({
                                question: legendText,
                                field_type: 'radio',
                                options: Array.from(fieldset.querySelectorAll('label')).map(l => l.innerText.trim()).filter(Boolean),
                                current_value: '',
                                is_required: input.required
                            });
                            continue;
                        }
                    }
                    const container = input.closest('fieldset, div');
                    if (container) {
                        options = Array.from(container.querySelectorAll('label')).map(l => l.innerText.trim()).filter(Boolean);
                    }
                } else if (input.type === 'checkbox') {
                    field_type = 'checkbox';
                } else {
                    current_value = input.value || '';
                }

                questions.push({
                    question: questionText,
                    field_type: field_type,
                    options: options,
                    current_value: current_value,
                    is_required: label.getAttribute('aria-required') === 'true' ||
                                 (input && input.required)
                });
            }

            // Strategy 3: find Required radio questions not caught by Strategy 1/2
            // LinkedIn often has Required radio questions like "Are you comfortable working remotely?"
            // that appear as standalone label+radio groups outside .fb-dash-form-element
            const requiredRadios = modal.querySelectorAll('[aria-required="true"], .jobs-easy-apply-form-section__grouping [required]');
            for (const reqEl of requiredRadios) {
                // Walk up to find the container with label text
                let container = reqEl.closest('fieldset, div[role="radiogroup"], .fb-dash-form-element');
                if (!container) container = reqEl.parentElement;
                if (!container) continue;

                // Find the question text — look for a label/sibling with text
                let questionText = '';
                const labels = container.querySelectorAll('label, span, legend');
                for (const l of labels) {
                    const t = l.innerText.trim();
                    if (t && !['yes', 'no', 'other', 'none'].includes(t.toLowerCase()) &&
                        !t.toLowerCase().includes('deselect resume') && !t.toLowerCase().includes('remove resume')) {
                        questionText = t;
                        break;
                    }
                }
                if (!questionText) {
                    // Try parent's text content before the radio group
                    const parent = container.parentElement;
                    if (parent) {
                        const textNodes = parent.innerText.split('\\n').filter(t => t.trim());
                        for (const t of textNodes) {
                            if (t.includes('?') || t.toLowerCase().includes('required')) {
                                questionText = t.replace(/\\s*Required\\s*/i, '').trim();
                                break;
                            }
                        }
                    }
                }
                if (!questionText || seen.has(questionText)) continue;
                if (['yes', 'no', 'other', 'none'].includes(questionText.toLowerCase())) continue;
                seen.add(questionText);

                // Find radio options
                const radios = container.querySelectorAll('input[type="radio"], div[role="radio"]');
                const radioOptions = [];
                for (const r of radios) {
                    const rl = r.closest('label') || r.parentElement;
                    const optText = rl ? rl.innerText.trim() : '';
                    if (optText && !radioOptions.includes(optText)) {
                        radioOptions.push(optText);
                    }
                }
                if (radioOptions.length === 0) continue;

                questions.push({
                    question: questionText,
                    field_type: 'radio',
                    options: radioOptions,
                    current_value: '',
                    is_required: true
                });
            }

            return questions;
        }
        """

        try:
            raw_questions = await page.evaluate(js_script)
            questions = raw_questions if isinstance(raw_questions, list) else []
        except PlaywrightError as e:
            logger.error(f"Failed to extract screening questions: {e}")

        return questions

    async def fill_answer(self, question: dict[str, Any], answer: str) -> bool:
        """Fill an answer for a screening question in the current modal step."""
        page = self._engine.page

        field_type = question.get("field_type", "text")
        question_text = question.get("question", "")
        current_value = question.get("current_value", "")

        # Skip fields that are already filled with a real value (not placeholder)
        if current_value and field_type == "dropdown":
            placeholder_values = ("select an option", "none", "n/a", "other", "")
            if current_value.lower().strip() not in placeholder_values:
                logger.debug(f"Skipping pre-filled dropdown: {question_text} = {current_value}")
                return True

        # Skip non-fillable question types
        if question_text.lower().startswith("deselect resume") or question_text.lower().startswith("follow "):
            logger.debug(f"Skipping non-fillable question: {question_text}")
            return True

        try:
            if field_type == "text":
                question_lower = question_text.lower()
                is_location_field = any(kw in question_lower for kw in ["location", "city", "country", "residence"])
                if is_location_field:
                    loc_answer = "Pune Division, Maharashtra, India" if ("pune" in answer.lower() or not answer or answer.lower() in ("n/a", "none")) else answer
                    result = await self._fill_combobox_answer(question_text, loc_answer)
                    logger.debug(f"fill_answer combobox '{question_text}' = '{loc_answer}': {result}")
                    if result:
                        return True

                safe_answer = json.dumps(answer)
                safe_question = json.dumps(question_text)
                js_fill = f"""
                () => {{
                    const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                    if (!modal) return false;
                    const qText = {safe_question};
                    const norm = s => (s || '').toLowerCase().replace(/[*?]/g, '').replace(/\\s+/g, ' ').trim();
                    const cleanQ = norm(qText);

                    // Strategy 1: Find container matching question_text
                    const containers = modal.querySelectorAll('.fb-dash-form-element, .jobs-easy-apply-form-section__grouping, fieldset, div');
                    for (const c of containers) {{
                        const labelEl = c.querySelector('label, legend, span.t-14');
                        if (labelEl) {{
                            const lt = norm(labelEl.innerText);
                            if (lt === cleanQ || lt.includes(cleanQ) || cleanQ.includes(lt)) {{
                                const input = c.querySelector('input[type="text"], input[type="number"], textarea');
                                if (input && input.offsetParent !== null) {{
                                    input.focus();
                                    const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                                    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                                    nativeSetter.call(input, {safe_answer});
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                    return true;
                                }}
                            }}
                        }}
                    }}

                    // Strategy 2: Find label matching question_text and walk up to find input
                    const labels = modal.querySelectorAll('label, legend');
                    for (const label of labels) {{
                        const lt = norm(label.innerText);
                        if (lt === cleanQ || lt.includes(cleanQ) || cleanQ.includes(lt)) {{
                            const forId = label.getAttribute('for');
                            let input = forId ? document.getElementById(forId) : null;
                            if (!input) {{
                                let parent = label.parentElement;
                                for (let i = 0; i < 4 && parent; i++) {{
                                    input = parent.querySelector('input[type="text"], input[type="number"], textarea');
                                    if (input) break;
                                    parent = parent.parentElement;
                                }}
                            }}
                            if (input && input.offsetParent !== null) {{
                                input.focus();
                                const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                                nativeSetter.call(input, {safe_answer});
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                    }}

                    // Fallback: fill first empty input
                    const inputs = modal.querySelectorAll('input[type="text"], input[type="number"], textarea');
                    for (const input of inputs) {{
                        if (input.offsetParent !== null && !input.value) {{
                            input.focus();
                            const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                            const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                            nativeSetter.call(input, {safe_answer});
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                            return true;
                        }}
                    }}

                    return false;
                }}
                """
                result = await page.evaluate(js_fill)
                logger.debug(f"fill_answer text '{question_text}' = '{answer}': {result}")
                return result

            elif field_type == "dropdown":
                options = question.get("options", [])
                if options:
                    best_match = self._find_best_option(answer, options)
                    if best_match:
                        result = await self._click_dropdown_option(best_match, question_text=question_text)
                        logger.debug(f"fill_answer dropdown '{question_text}' = '{best_match}': {result}")
                        return result

            elif field_type == "radio":
                options = question.get("options", [])
                if options:
                    best_match = self._find_best_option(answer, options)
                    if best_match:
                        result = await self._click_radio_option(best_match, question_text=question_text)
                        logger.debug(f"fill_answer radio '{question_text}' = '{best_match}': {result}")
                        return result

        except PlaywrightError as e:
            logger.error(f"Failed to fill answer: {e}")

        return False

    async def click_next(self) -> bool:
        """Click the Next/Continue button in the multi-step form."""
        page = self._engine.page
        try:
            result = await page.evaluate("""
            () => {
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const btns = modal.querySelectorAll('button');
                for (const b of btns) {
                    const text = (b.innerText || '').trim().toLowerCase();
                    const label = (b.getAttribute('aria-label') || '').toLowerCase();
                    if ((text.includes('next') || text.includes('continue') || label.includes('next') || label.includes('continue')) && b.offsetParent !== null && !b.disabled) {
                        b.click();
                        return true;
                    }
                }
                // Fallback: try any enabled primary button that isn't blacklisted
                const blacklist = ['submit', 'review', 'back', 'dismiss', 'close', 'cancel', 'skip', 'delete', 'remove', 'discard', 'save & exit', 'save and exit', 'exit', 'x'];
                for (const b of btns) {
                    const text = (b.innerText || '').trim().toLowerCase();
                    const label = (b.getAttribute('aria-label') || '').toLowerCase();
                    if (b.offsetParent !== null && !b.disabled
                        && !blacklist.some(w => text.includes(w) || label.includes(w))
                        && text.length > 0) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }
            """)
            return result
        except PlaywrightError as e:
            logger.debug(f"Failed to click next: {e}")
        return False

    async def click_review(self) -> bool:
        """Click the Review button."""
        page = self._engine.page
        try:
            result = await page.evaluate("""
            () => {
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const btns = modal.querySelectorAll('button');
                for (const b of btns) {
                    const text = (b.innerText || '').trim().toLowerCase();
                    const label = (b.getAttribute('aria-label') || '').toLowerCase();
                    if ((text.includes('review') || label.includes('review')) && b.offsetParent !== null && !b.disabled) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }
            """)
            return result
        except PlaywrightError as e:
            logger.debug(f"Failed to click review: {e}")
        return False

    async def submit_application(self) -> bool:
        """Click the Submit button to finalize the application."""
        page = self._engine.page
        try:
            result = await page.evaluate("""
            () => {
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const btns = modal.querySelectorAll('button');
                for (const b of btns) {
                    const text = (b.innerText || '').trim().toLowerCase();
                    const label = (b.getAttribute('aria-label') || '').toLowerCase();
                    if ((text.includes('submit') || label.includes('submit')) && b.offsetParent !== null && !b.disabled) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }
            """)
            return result
        except PlaywrightError as e:
            logger.debug(f"Failed to submit application: {e}")
        return False

    async def has_submit_success(self) -> bool:
        """Check if the application was submitted successfully.

        Success is detected when:
        1. Modal shows success text ("Application sent", etc.) without action buttons, OR
        2. The Easy Apply modal has completely disappeared from the DOM (modal-closed = success
           after a Submit click), OR
        3. A post-submission screen is shown (e.g. "Done" button only).
        """
        page = self._engine.page
        try:
            result = await page.evaluate("""
            () => {
                const modal = document.querySelector('div.jobs-easy-apply-modal, div[role="dialog"], div.artdeco-modal');
                // Modal gone entirely — if we previously had one open and it
                // disappeared, that means the application was accepted.
                if (!modal) return {success: true, reason: 'modal_gone', text: '', buttons: []};

                // Modal exists but might be a different dialog (e.g. success overlay)
                const text = (modal.innerText || '').toLowerCase();
                const btns = [];
                modal.querySelectorAll('button').forEach(b => {
                    if (b.offsetParent !== null) btns.push((b.innerText || '').trim().toLowerCase());
                });

                const hasSubmitBtn = btns.some(t => t.includes('submit'));
                const hasReviewBtn = btns.some(t => t.includes('review'));
                const hasNextBtn = btns.some(t => t.includes('next') || t.includes('continue'));
                const hasActionBtn = hasSubmitBtn || hasReviewBtn || hasNextBtn;

                // Check for visible input fields (excluding hidden inputs)
                const inputs = Array.from(modal.querySelectorAll('input:not([type="hidden"]), select, textarea'));
                const hasVisibleInputs = inputs.some(i => i.offsetParent !== null);

                // Check for success text
                const hasSuccessText = (
                    text.includes('application sent') ||
                    text.includes('your application was sent') ||
                    text.includes('successfully') ||
                    text.includes('thank you for applying') ||
                    text.includes('your application is all set') ||
                    text.includes('congratulations') ||
                    text.includes('submitted') ||
                    text.includes('application has been submitted')
                );

                // Post-submission screen: only "Done" or "Dismiss" buttons, plus success text
                const onlyDoneOrDismiss = btns.length > 0 && btns.every(
                    t => t.includes('done') || t.includes('dismiss') || t.includes('close') || t === 'x' || t === '×'
                );

                // It is NOT a success if there are still visible input fields we need to fill
                let success = false;
                if (!hasVisibleInputs) {
                    success = (hasSuccessText && !hasActionBtn) ||
                              (hasSuccessText && onlyDoneOrDismiss) ||
                              (onlyDoneOrDismiss && !hasActionBtn);
                }

                return {
                    success: success,
                    reason: success ? 'success_text' : (hasVisibleInputs ? 'has_visible_inputs' : (hasActionBtn ? 'has_action_btn' : 'no_success_text')),
                    text: text.substring(0, 200),
                    buttons: btns
                };
            }
            """)
            if not isinstance(result, dict):
                logger.debug(f"Submit success check: non-dict result {type(result).__name__}")
                return False
            logger.debug(f"Submit success check: {result.get('reason')} — buttons: {result.get('buttons', [])} — text: {result.get('text', '')[:80]}")
            return result.get('success', False)
        except PlaywrightError:
            # If we can't evaluate JS, the page may have navigated away (also a success signal)
            return False

    async def get_modal_text(self) -> str:
        """Get the text content of the Easy Apply modal for debugging."""
        page = self._engine.page
        try:
            return await page.evaluate("""
            () => {
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                return modal ? (modal.innerText || '').substring(0, 500) : 'NO MODAL FOUND';
            }
            """)
        except PlaywrightError:
            return 'ERROR READING MODAL'

    async def close_apply_modal(self) -> None:
        """Close the Easy Apply modal, including handling the 'Discard application?' confirmation."""
        page = self._engine.page

        # Step 1: Click the dismiss/close button on the modal
        try:
            await page.evaluate("""
            () => {
                // Try X button
                const modal = document.querySelector('div[role="dialog"]');
                if (modal) {
                    const closeBtn = modal.querySelector('button[aria-label="Dismiss" i], button[aria-label="Close" i], button.artdeco-modal__dismiss');
                    if (closeBtn) { closeBtn.click(); return; }
                }
                // Try overlay dismiss
                const dismiss = document.querySelector('button.artdeco-modal__dismiss, button[aria-label="Dismiss" i]');
                if (dismiss) dismiss.click();
            }
            """)
        except PlaywrightError:
            pass
        await asyncio.sleep(1.5)

        # Step 2: Handle "Discard application?" confirmation dialog
        # LinkedIn shows a second dialog asking "Are you sure you want to discard?"
        try:
            discard_clicked = await page.evaluate("""
            () => {
                // Look for discard confirmation dialog
                const dialogs = document.querySelectorAll('div[role="dialog"], div[role="alertdialog"]');
                for (const dialog of dialogs) {
                    const text = (dialog.innerText || '').toLowerCase();
                    if (text.includes('discard') || text.includes('are you sure') || text.includes('unsaved')) {
                        const btns = dialog.querySelectorAll('button');
                        for (const btn of btns) {
                            const btnText = (btn.innerText || '').trim().toLowerCase();
                            const btnLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                            if (btnText.includes('discard') || btnLabel.includes('discard')) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                }
                return false;
            }
            """)
            if discard_clicked:
                logger.debug("Clicked 'Discard' on confirmation dialog")
                await asyncio.sleep(1)
        except PlaywrightError:
            pass

        # Step 3: Verify the modal is actually closed — if not, try Escape key
        try:
            still_open = await page.evaluate("""
            () => {
                const m = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                return m && m.offsetParent !== null;
            }
            """)
            if still_open:
                logger.debug("Modal still open after dismiss — pressing Escape")
                await page.keyboard.press('Escape')
                await asyncio.sleep(1)
                # Check for discard dialog again after Escape
                try:
                    await page.evaluate("""
                    () => {
                        const dialogs = document.querySelectorAll('div[role="dialog"], div[role="alertdialog"]');
                        for (const dialog of dialogs) {
                            const text = (dialog.innerText || '').toLowerCase();
                            if (text.includes('discard') || text.includes('are you sure')) {
                                const btns = dialog.querySelectorAll('button');
                                for (const btn of btns) {
                                    const btnText = (btn.innerText || '').trim().toLowerCase();
                                    if (btnText.includes('discard')) { btn.click(); return; }
                                }
                            }
                        }
                    }
                    """)
                except PlaywrightError:
                    pass
                await asyncio.sleep(1)
        except PlaywrightError:
            pass

    async def unfollow_company(self) -> None:
        """Uncheck the follow company checkbox if present."""
        page = self._engine.page
        try:
            follow_checkbox = await page.query_selector(JobDetailSelectors.FOLLOW_COMPANY_CHECKBOX)
            if follow_checkbox:
                is_checked = await follow_checkbox.is_checked()
                if is_checked:
                    await follow_checkbox.click()
                    logger.debug("Unchecked follow company checkbox")
        except PlaywrightError:
            pass

    async def upload_resume_file(self, file_path: str) -> bool:
        """Upload a resume file to the file input in the modal."""
        page = self._engine.page
        try:
            import os
            if not os.path.isfile(file_path):
                logger.warning(f"Resume file not found: {file_path}")
                return False
            file_input = await page.query_selector('div[role="dialog"] input[type="file"]')
            if not file_input:
                file_input = await page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(file_path)
                await asyncio.sleep(2)
                logger.info(f"Resume uploaded: {file_path}")
                return True
            logger.warning("No file input found in modal")
            return False
        except PlaywrightError as e:
            logger.error(f"Failed to upload resume: {e}")
            return False

    def _find_best_option(self, target: str, options: list[str]) -> str | None:
        """Find the best matching option from a list using fuzzy matching."""
        if not options:
            return None

        target_lower = target.lower().strip()

        # Exact match
        for opt in options:
            if target_lower == opt.lower().strip():
                return opt

        # Contains match
        for opt in options:
            if target_lower in opt.lower() or opt.lower() in target_lower:
                return opt

        # Word overlap
        target_words = set(target_lower.split())
        best_score = 0
        best_option = None
        for opt in options:
            opt_words = set(opt.lower().split())
            overlap = len(target_words & opt_words)
            if overlap > best_score:
                best_score = overlap
                best_option = opt

        return best_option

    async def _click_dropdown_option(self, option_text: str, question_text: str = "") -> bool:
        """Click a specific option in a LinkedIn dropdown using Playwright select_option.
        
        Finds the SELECT element associated with the question's label, then selects
        the matching option. This avoids hitting the wrong SELECT when multiple exist.
        Uses textContent as fallback when innerText returns empty.
        """
        page = self._engine.page
        try:
            import json as _json
            safe_opt = _json.dumps(option_text)
            safe_q = _json.dumps(question_text) if question_text else ""

            # Strategy 1: Find the SELECT associated with this question's label
            if question_text:
                result = await page.evaluate(f"""
                () => {{
                    const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                    if (!modal) return null;
                    const qText = {safe_q};
                    const answer = {safe_opt};
                    
                    // Find label matching this question
                    const labels = modal.querySelectorAll('label');
                    for (const label of labels) {{
                        const lt = (label.textContent || label.innerText || '').trim();
                        if (lt === qText || lt.includes(qText) || qText.includes(lt)) {{
                            // Find associated SELECT via for=, or nearby
                            const forId = label.getAttribute('for');
                            let sel = forId ? document.getElementById(forId) : null;
                            if (!sel) sel = label.querySelector('select');
                            if (!sel) {{
                                const parent = label.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__grouping, div');
                                if (parent) sel = parent.querySelector('select');
                            }}
                            if (sel && sel.tagName === 'SELECT') {{
                                for (const opt of sel.options) {{
                                    if (opt.text.trim().toLowerCase() === answer.toLowerCase() ||
                                        opt.text.trim().toLowerCase().includes(answer.toLowerCase())) {{
                                        return {{selId: sel.id || null, value: opt.value, text: opt.text.trim()}};
                                    }}
                                }}
                            }}
                            // If no match found on this SELECT, try walking up more
                            const containers = label.closest('.jobs-easy-apply-form-section__grouping, .fb-dash-form-element, fieldset');
                            if (containers) {{
                                const selects = containers.querySelectorAll('select');
                                for (const sel of selects) {{
                                    for (const opt of sel.options) {{
                                        if (opt.text.trim().toLowerCase() === answer.toLowerCase() ||
                                            opt.text.trim().toLowerCase().includes(answer.toLowerCase())) {{
                                            return {{selId: sel.id || null, value: opt.value, text: opt.text.trim()}};
                                        }}
                                    }}
                                }}
                            }}
                        }}
                    }}
                    return null;
                }}
                """)
                if result:
                    # Use Playwright to select via the found selector
                    sel_info = result
                    try:
                        if sel_info.get('selId'):
                            sel_el = await page.query_selector(f'#{sel_info["selId"]}')
                        else:
                            sel_el = None
                        if sel_el:
                            await sel_el.select_option(value=sel_info['value'], timeout=3000)
                            await asyncio.sleep(0.3)
                            actual = await sel_el.evaluate("el => el.options[el.selectedIndex]?.text || ''")
                            logger.debug(f"Dropdown set via label-based select: '{actual}' (expected '{sel_info['text']}')")
                            return True
                    except PlaywrightError as e:
                        logger.debug(f"Label-based select_option failed: {e}")

            # Strategy 2: Find ALL visible selects, find first with matching option
            selects = await page.query_selector_all('div[role="dialog"] select')
            for sel in selects:
                is_hidden = await sel.evaluate("el => el.offsetParent === null || el.style.display === 'none'")
                if is_hidden:
                    continue
                options_data = await sel.evaluate("""(el) => {
                    return Array.from(el.options).map(o => ({text: o.text.trim(), value: o.value}))
                }""")
                target_lower = option_text.lower().strip()
                for opt in options_data:
                    if target_lower == opt['text'].lower() or target_lower in opt['text'].lower() or opt['text'].lower() in target_lower:
                        try:
                            await sel.select_option(value=opt['value'], timeout=3000)
                            await asyncio.sleep(0.3)
                            return True
                        except PlaywrightError:
                            pass

            # Strategy 3: Handle div[role="listbox"] / div[role="combobox"] (modern LinkedIn dropdowns)
            # Used especially for location/country/state/city pickers
            if question_text:
                listbox_found = await page.evaluate(f"""
                () => {{
                    const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                    if (!modal) return false;
                    const qText = {safe_q};
                    const answer = {safe_opt};

                    // Find label matching this question
                    const labels = modal.querySelectorAll('label');
                    for (const label of labels) {{
                        const lt = (label.innerText || '').trim();
                        if (lt === qText || lt.includes(qText) || qText.includes(lt)) {{
                            // Find associated listbox via for=, or nearby
                            const forId = label.getAttribute('for');
                            let targetInput = forId ? document.getElementById(forId) : null;
                            if (!targetInput) targetInput = label.querySelector('input, div[role="combobox"]');
                            if (!targetInput) {{
                                const parent = label.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__grouping, div');
                                if (parent) targetInput = parent.querySelector('div[role="combobox"], input');
                            }}

                            // Find the listbox container (sibling, or within the same section)
                            let listbox = null;
                            if (targetInput) {{
                                listbox = targetInput.parentElement.querySelector('div[role="listbox"]');
                            }}
                            if (!listbox) {{
                                // Try finding listbox within the form section
                                const section = label.closest('.jobs-easy-apply-form-section__grouping, .fb-dash-form-element');
                                if (section) {{
                                    listbox = section.querySelector('div[role="listbox"]');
                                }}
                            }}
                            if (!listbox) {{
                                // Last resort: find any listbox in the modal
                                listbox = modal.querySelector('div[role="listbox"]');
                            }}
                            if (!listbox) return false;

                            // Try clicking the combobox/input first to open the dropdown
                            if (targetInput && targetInput.tagName !== 'INPUT') {{
                                targetInput.click();
                            }}

                            // Look for matching option
                            const options = listbox.querySelectorAll('[role="option"]');
                            for (const opt of options) {{
                                const optText = (opt.innerText || opt.getAttribute('aria-label') || '').trim().toLowerCase();
                                if (optText === answer.toLowerCase() || optText.includes(answer.toLowerCase())) {{
                                    opt.click();
                                    return true;
                                }}
                            }}
                            // Try partial match (e.g., "India" matches "India (IN)")
                            for (const opt of options) {{
                                const optText = (opt.innerText || opt.getAttribute('aria-label') || '').trim().toLowerCase();
                                if (answer.toLowerCase().includes(optText) || answer.split(',')[0].trim().toLowerCase() === optText) {{
                                    opt.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                    }}
                    return false;
                }}
                """)
                if listbox_found:
                    await asyncio.sleep(0.5)
                    return True

            # Strategy 4: Fallback — find ANY div[role="listbox"] in modal and try matching
            listbox_found = await page.evaluate(f"""
            () => {{
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const answer = {safe_opt};

                const listboxes = modal.querySelectorAll('div[role="listbox"]');
                for (const listbox of listboxes) {{
                    const options = listbox.querySelectorAll('[role="option"]');
                    for (const opt of options) {{
                        const optText = (opt.innerText || opt.getAttribute('aria-label') || '').trim().toLowerCase();
                        if (optText === answer.toLowerCase() || optText.includes(answer.toLowerCase()) || answer.toLowerCase().includes(optText)) {{
                            // Click the trigger input first if it exists
                            const parent = listbox.parentElement;
                            const trigger = parent ? parent.querySelector('div[role="combobox"], input') : null;
                            if (trigger && trigger.tagName !== 'INPUT') {{
                                trigger.click();
                                // Small delay for dropdown animation
                            }}
                            opt.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}
            """)
            if listbox_found:
                await asyncio.sleep(0.5)
                return True

        except PlaywrightError as e:
            logger.debug(f"Failed to click dropdown option: {e}")
        return False

    async def _click_radio_option(self, option_text: str, question_text: str = "") -> bool:
        """Click a radio button option, scoped to question_text container if provided."""
        page = self._engine.page
        try:
            import json as _json
            safe_opt = _json.dumps(option_text)
            safe_q = _json.dumps(question_text)
            result = await page.evaluate(f"""
            () => {{
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const optStr = {safe_opt}.toLowerCase().trim();
                const qStr = {safe_q}.toLowerCase().trim();

                const norm = s => (s || '').toLowerCase().replace(/[*?]/g, '').replace(/\\s+/g, ' ').trim();

                // 1. Scoped search: Find form container matching question_text
                let targetContainer = null;
                if (qStr) {{
                    const containers = modal.querySelectorAll('.fb-dash-form-element, .jobs-easy-apply-form-section__grouping, fieldset, div[role="radiogroup"]');
                    for (const c of containers) {{
                        const ct = norm(c.innerText);
                        const cleanQ = norm(qStr);
                        if (ct.includes(cleanQ) || cleanQ.includes(ct.substring(0, 30))) {{
                            targetContainer = c;
                            break;
                        }}
                    }}
                }}

                const scope = targetContainer || modal;

                // Try native radio inside scope
                const radios = scope.querySelectorAll('input[type="radio"]');
                for (const radio of radios) {{
                    const label = radio.closest('label') || radio.parentElement;
                    if (label && norm(label.innerText).includes(optStr)) {{
                        radio.focus();
                        radio.click();
                        radio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}

                // Try custom radio divs inside scope
                const customRadios = scope.querySelectorAll('div[role="radio"]');
                for (const r of customRadios) {{
                    if (norm(r.innerText).includes(optStr)) {{
                        r.click();
                        return true;
                    }}
                }}

                // Fallback to global modal search if scoped search failed
                if (targetContainer) {{
                    const globalRadios = modal.querySelectorAll('input[type="radio"]');
                    for (const radio of globalRadios) {{
                        const label = radio.closest('label') || radio.parentElement;
                        if (label && norm(label.innerText).includes(optStr)) {{
                            radio.click();
                            return true;
                        }}
                    }}
                }}

                return false;
            }}
            """)
            return result
        except PlaywrightError as e:
            logger.debug(f"Failed to click radio option: {e}")
        return False

    async def _fill_combobox_answer(self, question_text: str, answer: str) -> bool:
        """Fill a typeahead combobox input (like Location city) and select matching option from dropdown."""
        page = self._engine.page
        try:
            import json as _json
            safe_q = _json.dumps(question_text)
            safe_ans = _json.dumps(answer)

            # Step 1: Type the search string into the combobox input
            typed = await page.evaluate(f"""
            () => {{
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const qText = {safe_q};
                const norm = s => (s || '').toLowerCase().replace(/[*?]/g, '').replace(/\\s+/g, ' ').trim();
                const cleanQ = norm(qText);

                // Find input element for this question
                let input = null;
                const labels = modal.querySelectorAll('label, legend');
                for (const label of labels) {{
                    const lt = norm(label.innerText);
                    if (lt === cleanQ || lt.includes(cleanQ) || cleanQ.includes(lt)) {{
                        const forId = label.getAttribute('for');
                        input = forId ? document.getElementById(forId) : null;
                        if (!input) {{
                            let parent = label.parentElement;
                            for (let i = 0; i < 4 && parent; i++) {{
                                input = parent.querySelector('input[role="combobox"], input[type="text"], input');
                                if (input) break;
                                parent = parent.parentElement;
                            }}
                        }}
                        if (input) break;
                    }}
                }}

                if (!input) {{
                    const inputs = modal.querySelectorAll('input[role="combobox"], input[type="text"]');
                    for (const inp of inputs) {{
                        if (inp.offsetParent !== null) {{
                            input = inp;
                            break;
                        }}
                    }}
                }}

                if (!input || input.offsetParent === null) return false;

                input.focus();
                input.value = '';
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                const searchStr = {safe_ans}.includes('Pune') ? 'Pune' : {safe_ans};
                nativeSetter.call(input, searchStr);
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            """)

            if not typed:
                logger.debug(f"Combobox input typing failed for '{question_text}'")
                return False

            await asyncio.sleep(1.5)

            # Step 2: Try clicking the matching option in the typeahead dropdown
            option_clicked = await page.evaluate(f"""
            () => {{
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal') || document.body;
                const target = {safe_ans}.toLowerCase().trim();

                const optionEls = modal.querySelectorAll('[role="option"], .basic-typeahead__typeahead-results li, .search-basic-typeahead-results li, li[role="option"], div[role="option"]');
                if (optionEls.length === 0) return false;

                const norm = s => (s || '').toLowerCase().replace(/[,\\s]+/g, ' ').trim();
                const targetNorm = norm(target);

                // 1. Try exact or full match (e.g. "pune division maharashtra india")
                for (const opt of optionEls) {{
                    const txt = norm(opt.innerText || opt.getAttribute('aria-label') || '');
                    if (txt === targetNorm || txt.includes(targetNorm) || targetNorm.includes(txt)) {{
                        opt.click();
                        return true;
                    }}
                }}

                // 2. Try partial match (e.g. "pune division")
                for (const opt of optionEls) {{
                    const txt = norm(opt.innerText || '');
                    if (txt.includes('pune division') || txt.includes('pune district') || txt.includes('pune city')) {{
                        opt.click();
                        return true;
                    }}
                }}

                // 3. Fallback to clicking the first visible option
                if (optionEls.length > 0 && optionEls[0].offsetParent !== null) {{
                    optionEls[0].click();
                    return true;
                }}

                return false;
            }}
            """)

            if option_clicked:
                logger.info(f"Combobox option clicked for '{question_text}' = '{answer}'")
                await asyncio.sleep(0.5)
                return True

            # Step 3: Keyboard fallback if DOM click didn't fire
            logger.debug(f"Combobox option click failed for '{question_text}' — using Keyboard fallback (ArrowDown + Enter)")
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.3)
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.5)
            return True

        except PlaywrightError as e:
            logger.debug(f"Combobox filling failed: {e}")
            return False
