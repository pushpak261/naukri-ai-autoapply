"""
JobDetailPage Page Object for Naukri.com.
Encapsulates parsing job details, detecting screening forms, answering questions, and submitting applications.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.config.constants import (
    ELEMENT_TIMEOUT,
    WORKER_GOTO_TIMEOUT,
    WORKER_NAV_SETTLE_TIMEOUT,
    ApplyFlowSelectors,
    JobDetailSelectors,
)
from src.naukri_agent.utils.helpers import clean_text
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


class JobDetailPage(BasePage):
    """
    Page Object representing the Naukri Job Details page.
    """

    async def navigate(self, url: str) -> None:
        """Navigate to a job detail page URL."""
        page = self._engine.page
        await page.goto(url, wait_until="domcontentloaded", timeout=WORKER_GOTO_TIMEOUT)
        await self._interactions.wait_for_navigation_complete(
            timeout=WORKER_NAV_SETTLE_TIMEOUT
        )
        await asyncio.sleep(1)

    async def is_already_applied(self) -> bool:
        """Check if the job has already been applied to."""
        if await self._interactions.element_exists(JobDetailSelectors.ALREADY_APPLIED):
            return True

        page = self._engine.page
        try:
            btn_texts = await page.evaluate(
                """
                () => {
                    const elements = [...document.querySelectorAll('button, a, .apply-button, .applyBtn, [class*="apply" i], [class*="walkin" i]')];
                    return elements.map(el => (el.textContent || '').trim().toLowerCase());
                }
                """
            )
            for text in btn_texts:
                if not text:
                    continue
                # Check for past-tense indicators of a completed application to avoid false positive on "apply"
                if any(
                    x in text
                    for x in [
                        "applied",
                        "already applied",
                        "submitted",
                        "received",
                        "application sent",
                        "you applied",
                    ]
                ):
                    return True
                if text in {"applied", "application submitted"}:
                    return True
        except PlaywrightError:
            pass

        return False

    async def is_external_apply(self) -> bool:
        """Check if the job apply button redirects to an external site."""
        return await self._interactions.element_exists(JobDetailSelectors.EXTERNAL_APPLY)

    async def get_job_details(self) -> dict:
        """
        Extract job details including description, key skills, experience, location, and salary.
        """
        page = self._engine.page
        # Scroll to simulate reading
        await self._interactions.random_scroll(scroll_count=2)

        # Extract description
        description = ""
        desc_elem = await page.query_selector(JobDetailSelectors.JOB_DESCRIPTION)
        if desc_elem:
            description = (await desc_elem.inner_text()) or ""
            description = clean_text(description)

        # Extract skills
        skill_elems = await page.query_selector_all(JobDetailSelectors.KEY_SKILLS)
        skills = []
        for se in skill_elems:
            skill_text = (await se.text_content() or "").strip()
            if skill_text:
                skills.append(skill_text)

        # Extract detailed fields
        experience = await self._interactions.get_text_content(JobDetailSelectors.EXPERIENCE_DETAIL)
        salary = await self._interactions.get_text_content(JobDetailSelectors.SALARY_DETAIL)
        location = await self._interactions.get_text_content(JobDetailSelectors.LOCATION_DETAIL)

        # Extract openings from body text
        openings = 0
        try:
            body_text = await page.evaluate("document.body.innerText")
            import re

            match = re.search(r"Openings:\s*(\d+)", body_text, re.IGNORECASE)
            if match:
                openings = int(match.group(1))
        except PlaywrightError as e:
            logger.debug(f"Failed to parse openings: {e}")

        # Check for company logo presence
        has_company_logo = await self._interactions.element_exists(
            JobDetailSelectors.COMPANY_LOGO_IMG
        )

        return {
            "description": description,
            "skills": ", ".join(skills),
            "experience_detail": clean_text(experience),
            "salary_detail": clean_text(salary),
            "location_detail": clean_text(location),
            "openings": openings,
            "has_company_logo": has_company_logo,
        }

    async def click_apply_button(self) -> bool:
        """
        Find and click the Apply button using multiple strategies.

        Returns:
            True if the button was clicked successfully.
        """
        # Strategy 1: XPath text-based selector
        clicked = await self._interactions.safe_click(
            JobDetailSelectors.APPLY_BUTTON, timeout=ELEMENT_TIMEOUT
        )
        if clicked:
            return True

        # Strategy 2: Additional XPath variations
        xpath_patterns = [
            '//a[contains(translate(., "APPLY", "apply"), "apply") and not(contains(translate(., "APPLIED", "applied"), "applied"))]',
            '//*[@role="button" and contains(translate(., "APPLY", "apply"), "apply") and not(contains(translate(., "APPLIED", "applied"), "applied"))]',
            '//input[@type="button" or @type="submit"][contains(translate(@value, "APPLY", "apply"), "apply")]',
            '//button[contains(translate(., "WALK-IN", "walk-in"), "walk-in") or contains(translate(., "WALKIN", "walkin"), "walkin")]',
            '//a[contains(translate(., "WALK-IN", "walk-in"), "walk-in") or contains(translate(., "WALKIN", "walkin"), "walkin")]',
        ]
        for pattern in xpath_patterns:
            clicked = await self._interactions.safe_click(pattern, timeout=3000)
            if clicked:
                return True

        # Strategy 3: Try common CSS patterns
        css_patterns = [
            'button[class*="apply"]',
            'button[id*="apply"]',
            'a[class*="apply"]',
            '[class*="apply-button"]',
            '[class*="applyBtn"]',
            'button[class*="walkin"]',
            'a[class*="walkin"]',
        ]
        for pattern in css_patterns:
            clicked = await self._interactions.safe_click(pattern, timeout=3000)
            if clicked:
                return True

        # Strategy 4: JavaScript click (bypasses overlays and handles non-standard elements)
        page = self._engine.page
        try:
            result = await page.evaluate(
                """
                () => {
                    const elements = [...document.querySelectorAll('button, a, input, [role="button"], [class*="apply" i], [class*="walkin" i]')];
                    
                    const visibleCandidates = elements.filter(el => {
                        try {
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) return false;
                            const style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                            return true;
                        } catch(e) {
                            return false;
                        }
                    });

                    // 1. Tag-specific check with strict text
                    for (const el of visibleCandidates) {
                        const tag = el.tagName.toLowerCase();
                        let text = (tag === 'input' ? (el.value || '') : (el.textContent || '')).trim().toLowerCase();
                        if (text.includes('applied') || text.includes('already applied')) continue;
                        
                        if (['button', 'a', 'input'].includes(tag) || el.getAttribute('role') === 'button') {
                            if (text === 'apply' || text === 'apply now' || text.startsWith('apply') || text.includes('walk-in') || text.includes('walkin') || text === 'interested') {
                                el.click();
                                return true;
                            }
                        }
                    }

                    // 2. Class/Id matching
                    for (const el of visibleCandidates) {
                        const tag = el.tagName.toLowerCase();
                        let text = (tag === 'input' ? (el.value || '') : (el.textContent || '')).trim().toLowerCase();
                        if (text.includes('applied') || text.includes('already applied')) continue;
                        
                        const id = (el.id || '').toLowerCase();
                        const className = (el.className || '').toString().toLowerCase();
                        
                        if (['button', 'a', 'input'].includes(tag) || el.getAttribute('role') === 'button') {
                            if (id.includes('apply') || className.includes('apply') || className.includes('walk-in') || className.includes('walkin')) {
                                el.click();
                                return true;
                            }
                        }
                    }

                    // 3. General text content matching
                    for (const el of visibleCandidates) {
                        let text = (el.textContent || '').trim().toLowerCase();
                        if (text.includes('applied') || text.includes('already applied')) continue;
                        
                        if (text === 'apply' || text === 'apply now' || text.includes('walk-in') || text.includes('walkin')) {
                            el.click();
                            return true;
                        }
                    }

                    return false;
                }
                """
            )
            if result:
                return True
        except PlaywrightError as e:
            logger.debug(f"JS apply click failed: {e}")

        return False

    async def is_chatbot_flow(self) -> bool:
        """Check if the current apply form is a chatbot interface."""
        return await self._interactions.element_exists(
            '[class*="chatbot-container"], [class*="bot-msg"], [class*="chatbot-msg"]'
        )

    async def _find_active_form_container(self):
        """Find the active apply/screening form or modal container."""
        page = self._engine.page
        selectors = [
            ApplyFlowSelectors.APPLY_FORM,
            ApplyFlowSelectors.FORM_FALLBACK,
            ApplyFlowSelectors.SCREENING_FALLBACK,
            '[class*="modal" i]',
            '[class*="popup" i]',
            '[class*="dialog" i]',
            "form",
        ]
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    if await el.is_visible():
                        return el
            except PlaywrightError:
                continue
        return None

    async def _is_apply_modal_visible(self) -> bool:
        """Check if an apply-specific modal/form is visible (not generic page forms)."""
        page = self._engine.page
        specific_selectors = [
            ApplyFlowSelectors.APPLY_FORM,
            ApplyFlowSelectors.FORM_FALLBACK,
            ApplyFlowSelectors.SCREENING_FALLBACK,
            '[class*="apply-modal"]',
            '[class*="apply-form"]',
            '[class*="chatbot"]',
            '[class*="chat" i]',
        ]
        for selector in specific_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    if await el.is_visible():
                        return True
            except PlaywrightError:
                continue
        return False

    async def _is_apply_button_present(self) -> bool:
        """Check if an active Apply button still exists on the page."""
        page = self._engine.page
        try:
            result = await page.evaluate("""
                () => {
                    const candidates = document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]');
                    for (const el of candidates) {
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        const text = (el.textContent || el.value || '').trim().toLowerCase();
                        if (text === 'apply' || text === 'apply now' || text.startsWith('apply ')) {
                            if (el.disabled) continue;
                            return true;
                        }
                    }
                    return false;
                }
            """)
            return result
        except Exception:
            return True  # Assume button is present if check fails (safe default)

    async def wait_for_apply_ui(self, timeout: int = 8000) -> bool:
        """Wait until an apply modal, form, or chatbot UI appears."""
        page = self._engine.page
        deadline = asyncio.get_event_loop().time() + (timeout / 1000)
        while asyncio.get_event_loop().time() < deadline:
            if await self._is_apply_modal_visible():
                return True
            if await self.is_chatbot_flow():
                return True
            url = page.url.lower()
            if any(token in url for token in ("myapply", "saveapply", "postapply")):
                return True
            questions = await self.extract_screening_questions()
            if questions:
                return True
            await asyncio.sleep(0.5)
        return await self._is_apply_modal_visible()

    async def detect_screening_questions(self) -> bool:
        """Check if the apply flow is showing screening questions."""
        page = self._engine.page
        url = page.url.lower()

        # If on dedicated apply flow URL, then questions exist
        if "naukri.com/myapply" in url or "saveapply" in url or "postapply" in url:
            return True

        # If it's a chatbot flow, it represents a screening questionnaire
        if await self.is_chatbot_flow():
            return True

        if await self._is_apply_modal_visible():
            questions = await self.extract_screening_questions()
            if questions:
                return True
            # Modal visible but no parsed fields yet — still treat as screening flow
            return True

        # Check using our robust extraction script
        questions = await self.extract_screening_questions()
        return len(questions) > 0

    async def extract_screening_questions(self) -> list[dict]:
        """
        Extract screening questions from the current apply form using a robust JS-based DOM engine.

        Returns:
            List of dicts with question text, type, and available options.
        """
        page = self._engine.page
        try:
            js_script = r"""
            () => {
                function hasVisibleBox(el) {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }

                // Helper to check if an element is visible
                function isVisible(el) {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    
                    const type = (el.getAttribute('type') || '').toLowerCase();
                    const tag = el.tagName.toLowerCase();
                    const role = (el.getAttribute('role') || '').toLowerCase();

                    // Radio/checkbox and opacity-0 inputs often have visible labels/parents
                    if (type === 'radio' || type === 'checkbox' || tag === 'input' || tag === 'textarea' || tag === 'select' || role === 'textbox' || role === 'combobox' || el.getAttribute('contenteditable') === 'true') {
                        const parentLabel = el.closest('label');
                        if (parentLabel && hasVisibleBox(parentLabel)) {
                            return true;
                        }
                        if (el.id) {
                            const label = document.querySelector('label[for="' + el.id + '"]');
                            if (label && hasVisibleBox(label)) {
                                return true;
                            }
                        }
                        const fieldParent = el.closest('[class*="field"], [class*="question"], [class*="form"], [class*="row"], [class*="input"], [class*="dropdown"], [class*="screening"], [class*="apply"]');
                        if (fieldParent && hasVisibleBox(fieldParent)) {
                            return true;
                        }
                    }

                    if (style.opacity === '0' || parseFloat(style.opacity) === 0) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }

                // Helper to clean question text
                function cleanQuestionText(text) {
                    if (!text) return "";
                    let cleaned = text.trim();
                    // Remove trailing colons, asterisks, spaces, newlines
                    cleaned = cleaned.replace(/[\*:\s]+$/, "");
                    cleaned = cleaned.replace(/^\s*[\*:\s]+/, "");
                    // Remove common labels like (Required), (Mandatory), etc.
                    cleaned = cleaned.replace(/\((required|mandatory|optional|must answer|choose)\)/gi, "");
                    return cleaned.trim();
                }

                // Helper to find the closest shared ancestor of multiple elements
                function findSharedAncestor(elements) {
                    if (elements.length === 0) return null;
                    if (elements.length === 1) return elements[0].parentElement;
                    let ancestor = elements[0].parentElement;
                    while (ancestor) {
                        if (elements.every(el => ancestor.contains(el))) {
                            return ancestor;
                        }
                        ancestor = ancestor.parentElement;
                    }
                    return document.body;
                }

                // Helper to get text content of an element excluding specific child elements (like option labels or inputs themselves)
                function getCleanedTextExcluding(element, excludeElements) {
                    let text = "";
                    for (let node of element.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            text += node.textContent;
                        } else if (node.nodeType === Node.ELEMENT_NODE) {
                            // If it is in excluded, skip
                            if (excludeElements.some(ex => ex === node || ex.contains(node))) {
                                continue;
                            }
                            text += " " + getCleanedTextExcluding(node, excludeElements);
                        }
                    }
                    return text;
                }

                // Helper to locate label text for a control group
                function getLabelForGroup(elements, formContainer) {
                    if (elements.length === 0) return "";
                    const first = elements[0];

                    // 1. Check for explicit label tag with 'for' attribute
                    if (first.id) {
                        const label = document.querySelector('label[for="' + first.id + '"]');
                        if (label && isVisible(label)) {
                            const text = label.innerText.trim();
                            if (text.length > 2) return text;
                        }
                    }

                    // 2. Check if first is inside a label tag
                    const parentLabel = first.closest('label');
                    if (parentLabel && isVisible(parentLabel)) {
                        const text = parentLabel.innerText.trim();
                        if (text.length > 2) return text;
                    }

                    // 3. Find closest shared ancestor container (like div.form-row)
                    let ancestor = findSharedAncestor(elements);
                    // Don't climb above form container
                    if (formContainer && formContainer.contains(ancestor) && ancestor !== formContainer) {
                        // Find all text inside ancestor excluding option inputs/labels themselves
                        // We want to collect the inputs and their parent labels (option labels) to exclude them
                        const optionLabelsAndInputs = [];
                        elements.forEach(el => {
                            optionLabelsAndInputs.push(el);
                            const parentLbl = el.closest('label');
                            if (parentLbl) optionLabelsAndInputs.push(parentLbl);
                        });

                        const ancestorText = getCleanedTextExcluding(ancestor, optionLabelsAndInputs).trim();
                        if (ancestorText.length > 3) {
                            return ancestorText;
                        }
                    }

                    // 4. Fallback to preceding sibling text
                    let prev = first.previousElementSibling;
                    while (prev) {
                        if (isVisible(prev)) {
                            const text = prev.innerText || prev.textContent || "";
                            if (text.trim().length > 3) return text.trim();
                        }
                        prev = prev.previousElementSibling;
                    }

                    // 5. Fallback to attributes
                    const placeholder = first.getAttribute('placeholder');
                    if (placeholder && placeholder.length > 2) return placeholder;
                    const name = first.getAttribute('name');
                    if (name && name.length > 2) return name;

                    return "";
                }

                // Identify the active form container
                const selectors = [
                    '[class*="apply-modal"]', '[class*="apply-form"]', 
                    '[class*="chatbot"]', '[class*="chat" i]', '[class*="bot" i]',
                    '[class*="modal" i]', '[class*="popup" i]', '[class*="dialog" i]',
                    'form[class*="apply"]', '[class*="screening"]', 'form', 'body'
                ];
                let formContainer = null;
                for (let sel of selectors) {
                    const elements = document.querySelectorAll(sel);
                    for (let el of elements) {
                        if (isVisible(el)) {
                            // Check if this container ACTUALLY HAS ANY INPUTS
                            const hasInputs = el.querySelector('input:not([type="hidden"]), select, textarea, [contenteditable="true"]');
                            if (hasInputs) {
                                formContainer = el;
                                break;
                            }
                        }
                    }
                    if (formContainer && formContainer.tagName !== 'BODY') break;
                }
                if (!formContainer) formContainer = document.body;

                // Find all visible interactive elements in formContainer
                let rawControls = Array.from(formContainer.querySelectorAll(
                    'input, select, textarea, [contenteditable="true"], [role="combobox"], [role="textbox"], [role="spinbutton"], [role="listbox"]'
                ));
                let visibleControls = rawControls.filter(el => {
                    if (!isVisible(el)) return false;
                    const type = (el.getAttribute('type') || '').toLowerCase();
                    // Ignore hidden, file, buttons
                    if (['hidden', 'submit', 'button', 'image', 'file'].includes(type)) return false;
                    // Ignore search bar and header/nav inputs to prevent false positives when falling back to body
                    if (el.closest('header, nav, [class*="header" i], [class*="nav" i], [class*="qsb" i], [class*="search-bar" i], [class*="searchBar" i]')) return false;
                    return true;
                });

                if (visibleControls.length === 0 && formContainer !== document.body) {
                    // Fallback to searching the entire body if the chosen container had no valid inputs
                    formContainer = document.body;
                    rawControls = Array.from(formContainer.querySelectorAll(
                        'input, select, textarea, [contenteditable="true"], [role="combobox"], [role="textbox"], [role="spinbutton"], [role="listbox"]'
                    ));
                    visibleControls = rawControls.filter(el => {
                        if (!isVisible(el)) return false;
                        const type = (el.getAttribute('type') || '').toLowerCase();
                        if (['hidden', 'submit', 'button', 'image', 'file'].includes(type)) return false;
                        if (el.closest('header, nav, [class*="header" i], [class*="nav" i], [class*="qsb" i], [class*="search-bar" i], [class*="searchBar" i]')) return false;
                        return true;
                    });
                }

                // Group elements by name/grouping
                const groups = [];
                const processedNames = new Set();

                visibleControls.forEach(control => {
                    const tagName = control.tagName.toLowerCase();
                    const typeAttr = (control.getAttribute('type') || '').toLowerCase();
                    const roleAttr = (control.getAttribute('role') || '').toLowerCase();
                    const name = control.getAttribute('name') || control.id || '';

                    if ((typeAttr === 'radio' || typeAttr === 'checkbox') && name) {
                        if (processedNames.has(name)) return;
                        processedNames.add(name);
                        // Find all sibling radio/checkbox inputs with the same name
                        const groupInputs = visibleControls.filter(el => {
                            const elType = (el.getAttribute('type') || '').toLowerCase();
                            return elType === typeAttr && (el.getAttribute('name') || el.id || '') === name;
                        });
                        groups.push({
                            type: typeAttr,
                            name: name,
                            elements: groupInputs
                        });
                    } else if (roleAttr === 'combobox' || roleAttr === 'listbox' || tagName === 'select') {
                        groups.push({
                            type: 'dropdown',
                            name: name,
                            elements: [control]
                        });
                    } else if (control.getAttribute('contenteditable') === 'true' || roleAttr === 'textbox' || roleAttr === 'spinbutton') {
                        groups.push({
                            type: tagName === 'textarea' ? 'text_area' : (roleAttr === 'spinbutton' ? 'number' : 'text'),
                            name: name,
                            elements: [control]
                        });
                    } else {
                        groups.push({
                            type: tagName === 'select' ? 'dropdown' : (tagName === 'textarea' ? 'text_area' : typeAttr || 'text'),
                            name: name,
                            elements: [control]
                        });
                    }
                });

                // Process each group to extract question info
                const questions = [];
                groups.forEach((group, index) => {
                    const fieldId = 'agent_q_' + index;
                    const rawQuestion = getLabelForGroup(group.elements, formContainer);
                    const cleanedQuestion = cleanQuestionText(rawQuestion);

                    // Determine if required
                    let required = false;
                    group.elements.forEach(el => {
                        if (el.hasAttribute('required') || el.getAttribute('aria-required') === 'true') {
                            required = true;
                        }
                    });
                    // Or check if rawQuestion has asterisk/required marker
                    if (rawQuestion.includes('*') || /required|mandatory|must\s*answer/i.test(rawQuestion)) {
                        required = true;
                    }

                    // Extract options if dropdown/radio/checkbox
                    let options = [];
                    let value = "";

                    if (group.type === 'dropdown') {
                        const selectEl = group.elements[0];
                        selectEl.setAttribute('data-agent-field-id', fieldId);
                        const tag = selectEl.tagName.toLowerCase();
                        if (tag === 'select') {
                            value = selectEl.value || "";
                            const optionElems = selectEl.querySelectorAll('option');
                            optionElems.forEach(opt => {
                                const optText = opt.textContent.trim();
                                const optVal = opt.value;
                                if (optText && !/select|choose|--/i.test(optText)) {
                                    options.push({ text: optText, value: optVal });
                                }
                            });
                        } else {
                            // Custom combobox/listbox (React dropdown)
                            value = (selectEl.innerText || selectEl.textContent || "").trim();
                            const optionRoot = selectEl.closest('[class*="field"], [class*="question"], [class*="form"], [class*="row"], [class*="dropdown"], [class*="select"]') || selectEl.parentElement;
                            if (optionRoot) {
                                const optCandidates = optionRoot.querySelectorAll('li, [role="option"], [class*="option"], button, label');
                                optCandidates.forEach((opt, optIdx) => {
                                    const optText = (opt.innerText || opt.textContent || "").trim();
                                    if (optText && optText.length < 120 && !/select|choose|submit|save|next|close/i.test(optText)) {
                                        const optFieldId = fieldId + '_opt_' + optIdx;
                                        opt.setAttribute('data-agent-field-id', optFieldId);
                                        options.push({
                                            text: optText,
                                            value: optText,
                                            selector: "[data-agent-field-id='" + optFieldId + "']"
                                        });
                                    }
                                });
                            }
                        }
                    } else if (group.type === 'radio' || group.type === 'checkbox') {
                        group.elements.forEach((el, optIdx) => {
                            const optFieldId = fieldId + '_opt_' + optIdx;
                            el.setAttribute('data-agent-field-id', optFieldId);
                            
                            // Find label text for this specific option
                            let optText = "";
                            const parentLabel = el.closest('label');
                            if (parentLabel) {
                                optText = parentLabel.innerText.trim();
                            } else if (el.id) {
                                const label = document.querySelector('label[for="' + el.id + '"]');
                                if (label) optText = label.innerText.trim();
                            }
                            if (!optText) optText = el.value || "";

                            if (el.checked) {
                                value = optText;
                            }

                            options.push({
                                text: optText,
                                value: el.value || "",
                                selector: "[data-agent-field-id='" + optFieldId + "']"
                            });
                        });
                    } else {
                        // Text, number, date, contenteditable, etc.
                        const inputEl = group.elements[0];
                        inputEl.setAttribute('data-agent-field-id', fieldId);
                        if (inputEl.getAttribute('contenteditable') === 'true') {
                            value = (inputEl.innerText || inputEl.textContent || "").trim();
                        } else {
                            value = inputEl.value !== undefined ? inputEl.value : (inputEl.innerText || inputEl.textContent || "");
                        }

                        // Refine type if text but matches certain patterns
                        let refinedType = group.type;
                        const qLower = cleanedQuestion.toLowerCase();
                        if (refinedType === 'text') {
                            if (qLower.includes('experience') || qLower.includes('years') || qLower.includes('ctc') || qLower.includes('salary') || qLower.includes('package') || qLower.includes('number') || qLower.includes('phone') || qLower.includes('mobile')) {
                                refinedType = 'number';
                            } else if (qLower.includes('date') || qLower.includes('dob') || qLower.includes('birth') || qLower.includes('joining')) {
                                refinedType = 'date';
                            }
                        }
                        group.type = refinedType;
                    }

                    // Skip if the question is blank and it's not a required text field
                    if (!cleanedQuestion && !required) return;

                    questions.push({
                        id: fieldId,
                        question: cleanedQuestion || ('Question ' + (index + 1)),
                        original_question: rawQuestion,
                        type: group.type,
                        options: options,
                        required: required,
                        selector: "[data-agent-field-id='" + fieldId + "']",
                        value: value
                    });
                });

                // Chatbot Flow Fallback if traditional questions are 0
                if (questions.length === 0) {
                    const chatbotMsgs = document.querySelectorAll('[class*="chatbot-msg"], [class*="bot-msg"], [class*="chat-msg"], [class*="msg-bubble"], [class*="message"]:not([class*="error"])');
                    if (chatbotMsgs.length > 0) {
                        const lastMsg = chatbotMsgs[chatbotMsgs.length - 1];
                        const msgText = (lastMsg.innerText || lastMsg.textContent || "").trim();
                        if (msgText) {
                            const chatbotContainer = lastMsg.closest('[class*="bot"], [class*="chat"]');
                            const options = [];
                            let chatbotInputSelector = "";

                            if (chatbotContainer) {
                                const optBtns = chatbotContainer.querySelectorAll('li, [class*="radio"], [class*="option"], button');
                                optBtns.forEach((opt, optIdx) => {
                                    const optText = opt.innerText.trim();
                                    if (optText && optText.length < 50 && !/save|submit|next|close/i.test(optText)) {
                                        const optFieldId = 'agent_chat_opt_' + optIdx;
                                        opt.setAttribute('data-agent-field-id', optFieldId);
                                        options.push({
                                            text: optText,
                                            value: optText,
                                            selector: "[data-agent-field-id='" + optFieldId + "']"
                                        });
                                    }
                                });
                            }

                            // Find the text input robustly, preferring inside the chatbot container but falling back to any visible non-search input
                            const inputCandidates = chatbotContainer 
                                ? Array.from(chatbotContainer.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea, [contenteditable="true"]'))
                                : [];
                                
                            if (inputCandidates.length === 0) {
                                const globals = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea, [contenteditable="true"]'));
                                globals.forEach(el => {
                                    if (isVisible(el) && !el.closest('header, nav, [class*="header" i], [class*="nav" i], [class*="qsb" i], [class*="search-bar" i], [class*="searchBar" i]')) {
                                        inputCandidates.push(el);
                                    }
                                });
                            }

                            if (inputCandidates.length > 0) {
                                const txtInput = inputCandidates[0];
                                const fieldId = "agent_chat_input";
                                txtInput.setAttribute('data-agent-field-id', fieldId);
                                chatbotInputSelector = "[data-agent-field-id='" + fieldId + "']";
                            }

                            questions.push({
                                id: "agent_chat_q",
                                question: cleanQuestionText(msgText),
                                original_question: msgText,
                                type: options.length > 0 ? "radio" : "text",
                                options: options,
                                required: true,
                                selector: chatbotInputSelector || "input:not([type='hidden'])",
                                value: ""
                            });
                        }
                    }
                }

                return JSON.stringify(questions);
            }
            """
            all_questions: list[dict] = []
            seen_ids: set[str] = set()

            def _merge_questions(batch: list[dict]) -> None:
                for q in batch:
                    qid = q.get("id") or q.get("question", "")
                    if qid and qid not in seen_ids:
                        seen_ids.add(qid)
                        all_questions.append(q)

            # Main frame
            result_json = await page.evaluate(js_script)
            _merge_questions(json.loads(result_json))

            # Child iframes (Naukri sometimes renders apply UI inside iframes)
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                with contextlib.suppress(Exception):
                    frame_json = await frame.evaluate(js_script)
                    _merge_questions(json.loads(frame_json))

            logger.info(f"Detected {len(all_questions)} screening questions")
            return all_questions
        except Exception as e:
            logger.error(f"Error during JS-based question extraction: {e}")
            return []

    async def fill_answer_by_metadata(self, question: dict, answer: str) -> bool:
        """
        Fill a question answer using precise metadata and selectors assigned during extraction.
        """
        page = self._engine.page
        q_type = question.get("type")
        q_text = question.get("question")
        selector = question.get("selector")
        answer = (answer or "").strip()
        if not answer:
            return False

        try:
            if q_type == "dropdown":
                select_elem = await page.query_selector(selector) if selector else None
                if select_elem:
                    tag = await select_elem.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        return await self._select_dropdown_option_by_metadata(
                            select_elem, question.get("options", []), answer
                        )
                    options = question.get("options", [])
                    await select_elem.scroll_into_view_if_needed()
                    await select_elem.click()
                    await asyncio.sleep(0.4)
                    if await self._select_choice_option_by_metadata(
                        options, answer, is_checkbox=False
                    ):
                        return True
                    return await self._click_visible_option_by_text(answer)
            elif q_type in ("radio", "checkbox"):
                options = question.get("options", [])
                if await self._select_choice_option_by_metadata(
                    options, answer, q_type == "checkbox"
                ):
                    return True
                return await self._click_visible_option_by_text(answer)
            else:
                input_elem = await page.query_selector(selector) if selector else None
                if input_elem:
                    await input_elem.scroll_into_view_if_needed()
                    is_contenteditable = await input_elem.evaluate(
                        'el => el.getAttribute("contenteditable") === "true"'
                    )
                    if is_contenteditable:
                        await input_elem.click()
                        await input_elem.evaluate(
                            "(el, val) => { el.textContent = val; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }",
                            answer,
                        )
                    else:
                        await input_elem.fill("")
                        await input_elem.type(answer, delay=50)
                    return True
        except Exception as e:
            logger.error(f"Failed to fill answer using metadata for '{q_text}': {e}")

        return False

    async def _click_visible_option_by_text(self, answer: str) -> bool:
        """Click a visible dropdown/list option by its label text."""
        page = self._engine.page
        answer = (answer or "").strip()
        if not answer:
            return False

        try:
            for role in ("option", "menuitem", "radio"):
                locator = page.get_by_role(role, name=answer)
                if await locator.count() > 0:
                    await locator.first.scroll_into_view_if_needed()
                    await locator.first.click(timeout=2000)
                    return True

            option_locator = page.locator(
                f'li:has-text("{answer}"), [role="option"]:has-text("{answer}"), '
                f'label:has-text("{answer}"), button:has-text("{answer}")'
            )
            if await option_locator.count() > 0:
                await option_locator.first.scroll_into_view_if_needed()
                await option_locator.first.click(timeout=2000)
                return True
        except PlaywrightError as e:
            logger.debug(f"Visible option click failed for '{answer}': {e}")
        return False

    async def fill_question_answer(self, question: dict, answer: str) -> bool:
        """Fill a screening answer using metadata selectors, then label-based fallbacks."""
        answer = (answer or "").strip()
        q_text = (question.get("question") or "").strip()
        if not answer:
            return False

        if await self.fill_answer_by_metadata(question, answer):
            return True

        if q_text:
            try:
                await self.fill_answer(q_text, answer)
                return True
            except Exception as e:
                logger.debug(f"Label-based fill failed for '{q_text}': {e}")

        return await self._click_visible_option_by_text(answer)

    async def _select_dropdown_option_by_metadata(
        self, select_elem, options: list[dict], answer: str
    ) -> bool:
        answer_lower = answer.lower().strip()

        # 1. Exact match on text or value
        for opt in options:
            o_text = opt.get("text", "").lower().strip()
            o_val = opt.get("value", "").lower().strip()
            if o_text == answer_lower or o_val == answer_lower:
                await select_elem.select_option(value=opt.get("value"))
                return True

        # 2. Substring match
        for opt in options:
            o_text = opt.get("text", "").lower().strip()
            o_val = opt.get("value", "").lower().strip()
            if answer_lower in o_text or o_text in answer_lower or answer_lower in o_val:
                await select_elem.select_option(value=opt.get("value"))
                return True

        # 3. Fallback: select first non-empty option
        if options:
            await select_elem.select_option(value=options[0].get("value"))
            return True

        return False

    async def _select_choice_option_by_metadata(
        self, options: list[dict], answer: str, is_checkbox: bool = False
    ) -> bool:
        page = self._engine.page
        answer_lower = answer.lower().strip()

        # Split answer by comma for multi-select checkboxes
        answers_list = (
            [a.strip() for a in answer_lower.split(",")] if is_checkbox else [answer_lower]
        )

        matched_any = False

        async def click_element_or_label(elem) -> bool:
            """Try to click the element or its parent/associated label for visibility safety."""
            clicked = False
            # Try parent label first
            try:
                parent_label = await elem.evaluate_handle("el => el.closest('label')")
                label_elem = parent_label.as_element()
                if label_elem:
                    await label_elem.scroll_into_view_if_needed()
                    await label_elem.click()
                    clicked = True
            except Exception:
                pass

            # Try associated label[for] next
            if not clicked:
                try:
                    elem_id = await elem.get_attribute("id")
                    if elem_id:
                        label_elem = await page.query_selector(f'label[for="{elem_id}"]')
                        if label_elem:
                            await label_elem.scroll_into_view_if_needed()
                            await label_elem.click()
                            clicked = True
                except Exception:
                    pass

            # Fallback to direct click
            if not clicked:
                try:
                    await elem.scroll_into_view_if_needed()
                    await elem.click()
                    clicked = True
                except Exception as e:
                    logger.debug(f"Direct click failed on element: {e}")
            return clicked

        for opt in options:
            o_text = opt.get("text", "").lower().strip()
            selector = opt.get("selector")

            # Check if option text matches any of the answers
            is_match = False
            for ans in answers_list:
                if ans == o_text or ans in o_text or o_text in ans:
                    is_match = True
                    break

            if is_match and selector:
                elem = await page.query_selector(selector)
                if elem:
                    success = await click_element_or_label(elem)
                    if success:
                        matched_any = True
                        if not is_checkbox:
                            return True

        # Fallback if no match: click the first option for radio
        if not matched_any and options and not is_checkbox:
            selector = options[0].get("selector")
            if selector:
                elem = await page.query_selector(selector)
                if elem:
                    success = await click_element_or_label(elem)
                    if success:
                        return True

        return matched_any

    async def fill_answer(self, question_text: str, answer: str) -> None:
        """Fill a single answer into the appropriate form field on the page.

        Robust strategy:
        1) Prefer associating by label[for] when possible.
        2) If not available, use DOM proximity within the label's parent/closest container.
        3) For dropdown/radio/checkbox, match/select by option text.
        4) For chatbot flow, click matching option inside the active chatbot container,
           else type into the chatbot text input and trigger Save/Submit/Enter.
        """
        page = self._engine.page
        q = (question_text or "").strip()
        a = (answer or "").strip()

        if not q or not a:
            logger.warning(f"Skipping fill: question or answer empty (q='{q}', a='{a[:30]}')")
            return

        answer_lower = a.lower().strip()

        # For chatbot, we do a dedicated fill first because labels may not exist.
        if await self.is_chatbot_flow():
            try:
                chatbot_msgs = await page.query_selector_all(
                    '[class*="chatbot-msg"], [class*="bot-msg"]'
                )
                if chatbot_msgs:
                    last_msg = chatbot_msgs[-1]
                    chatbot_container = await last_msg.evaluate_handle(
                        'el => el.closest(\'[class*="bot"], [class*="chat"]\')'
                    )
                    if chatbot_container and await chatbot_container.evaluate("el => el !== null"):
                        container_el = chatbot_container.as_element()

                        # 1) Try clickable options (radio/chips/buttons)
                        option_elems = await container_el.query_selector_all(
                            'li, [class*="radio"], [class*="option"], button'
                        )
                        for opt in option_elems:
                            opt_text = (await opt.text_content() or "").strip().lower()
                            if not opt_text:
                                continue
                            # exact, then contains in either direction
                            if (
                                answer_lower == opt_text
                                or answer_lower in opt_text
                                or opt_text in answer_lower
                            ):
                                await opt.click()
                                logger.debug(
                                    "Chatbot: clicked option for question '%s' with answer '%s' (option='%s')",
                                    q[:60],
                                    a[:60],
                                    opt_text[:60],
                                )
                                return

                        # 2) Try chatbot text input
                        text_inputs = await container_el.query_selector_all(
                            'input[type="text"], input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea'
                        )
                        for text_input in text_inputs:
                            await text_input.fill("")
                            await text_input.type(a, delay=50)

                            # Trigger next step
                            submit_btn = await container_el.query_selector(
                                'button:has-text("Save"), button:has-text("Submit"), button:has-text("Next"), button:has-text("Continue")'
                            )
                            if submit_btn and await submit_btn.is_visible(timeout=1000):
                                try:
                                    await submit_btn.click(timeout=1500)
                                except PlaywrightError:
                                    await text_input.press("Enter")
                            else:
                                await text_input.press("Enter")

                            logger.debug(
                                "Chatbot: typed into text input for question '%s' with answer '%s'",
                                q[:60],
                                a[:60],
                            )
                            return
            except PlaywrightError as e:
                logger.debug(f"Chatbot fill failed for '{q[:40]}': {e}")

        # Standard (non-chatbot) form fill.
        try:
            labels = await page.query_selector_all("label")

            # First pass: strict match by label[for] id
            for label in labels:
                label_text = (await label.text_content() or "").strip()
                if not label_text:
                    continue

                # allow minor differences: exact containment on full string rather than only prefix
                if (
                    q.lower() in label_text.lower()
                    or label_text.lower() in q.lower()
                    or q.lower()[:20] in label_text.lower()
                ):
                    label_for = await label.get_attribute("for")

                    input_elem = None
                    if label_for:
                        input_elem = await page.query_selector(f"#{label_for}")

                    # Proximity fallback
                    if not input_elem:
                        parent = await label.evaluate_handle(
                            "el => el.closest('fieldset, form, div')"
                        )
                        if parent:
                            input_elem = await parent.as_element().query_selector(
                                "input, select, textarea"
                            )

                    if not input_elem:
                        continue

                    tag = await input_elem.evaluate("el => el.tagName.toLowerCase()")

                    if tag == "select":
                        await self._select_dropdown_option(input_elem, a)
                        logger.debug(
                            "Standard: selected dropdown for question '%s' with answer '%s'",
                            q[:60],
                            a[:60],
                        )
                        return

                    if tag == "textarea":
                        await input_elem.fill(a)
                        logger.debug(
                            "Standard: filled textarea for question '%s' with answer '%s'",
                            q[:60],
                            a[:60],
                        )
                        return

                    # input kinds
                    input_type = (await input_elem.get_attribute("type") or "text").lower()
                    if input_type == "radio":
                        # Use labels inside the same container to pick exact option text.
                        await self._select_radio_option(label, a)
                        logger.debug(
                            "Standard: selected radio for question '%s' with answer '%s'",
                            q[:60],
                            a[:60],
                        )
                        return

                    if input_type == "checkbox":
                        is_checked = await input_elem.is_checked()
                        should_check = answer_lower in ("yes", "true", "checked", "1")
                        if should_check != is_checked:
                            await input_elem.click()
                        logger.debug(
                            "Standard: toggled checkbox for question '%s' to '%s'",
                            q[:60],
                            "checked" if should_check else "unchecked",
                        )
                        return

                    # text input
                    await input_elem.fill("")
                    await input_elem.type(a, delay=50)
                    logger.debug(
                        "Standard: filled input for question '%s' with answer '%s'",
                        q[:60],
                        a[:60],
                    )
                    return

            # Last resort: chatbot label-like buttons (some forms render choices as buttons)
            if await self.is_chatbot_flow():
                return

            logger.warning(
                "No UI control found for screening question. q='%s' a='%s'",
                q[:120],
                a[:120],
            )

        except PlaywrightError as e:
            logger.warning(f"Failed to fill answer for question '{q[:40]}': {e}")

    async def _select_dropdown_option(self, select_elem, answer: str) -> None:
        """Select the best matching option from a dropdown."""
        try:
            options = await select_elem.query_selector_all("option")
            answer_lower = answer.lower().strip()

            # Try exact match first
            for opt in options:
                opt_text = (await opt.text_content() or "").strip()
                opt_value = await opt.get_attribute("value") or ""
                if opt_text.lower() == answer_lower or opt_value.lower() == answer_lower:
                    await select_elem.select_option(value=opt_value)
                    return

            # Try partial match
            for opt in options:
                opt_text = (await opt.text_content() or "").strip()
                opt_value = await opt.get_attribute("value") or ""
                if answer_lower in opt_text.lower() or opt_text.lower() in answer_lower:
                    await select_elem.select_option(value=opt_value)
                    return

            logger.warning(f"No matching dropdown option for: {answer}")

        except PlaywrightError as e:
            logger.debug(f"Dropdown selection failed: {e}")

    async def _select_radio_option(self, label_elem, answer: str) -> None:
        """Select the best matching radio button option."""
        try:
            parent = await label_elem.evaluate_handle("el => el.closest('fieldset, div, form')")
            parent_elem = parent.as_element()
            if parent_elem:
                radio_labels = await parent_elem.query_selector_all("label")
                answer_lower = answer.lower().strip()

                for rl in radio_labels:
                    rl_text = (await rl.text_content() or "").strip()
                    if answer_lower in rl_text.lower() or rl_text.lower() in answer_lower:
                        radio = await rl.query_selector('input[type="radio"]')
                        if radio:
                            await radio.click()
                            return

        except PlaywrightError as e:
            logger.debug(f"Radio selection failed: {e}")

    async def submit_application(self) -> bool:
        """Click the submit/apply button to finalize the application.

        Returns:
            True if a button was successfully clicked, False otherwise.
        """
        page = self._engine.page

        # Try a robust JavaScript evaluator click first to find the best visible, enabled button
        js_click_script = """
        () => {
            const getScore = (el) => {
                const text = el.textContent.trim().toLowerCase() || el.value?.trim().toLowerCase() || "";
                let score = 0;
                if (text.includes("submit") || text === "apply" || text === "apply now") score = 100;
                else if (text.includes("save") || text.includes("next") || text.includes("continue") || text.includes("send")) score = 80;
                else if (text.includes("confirm") || text.includes("proceed")) score = 70;
                
                if (score > 0) {
                    // Boost score if inside a modal, popup, or chatbot container
                    if (el.closest('[class*="modal" i], [class*="dialog" i], [class*="popup" i], [class*="chatbot"], [class*="chat" i], [class*="bot" i], [class*="drawer" i]')) {
                        score += 50;
                    }
                }
                return score;
            };

            const candidates = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn, a.button, [class*="btn" i], [class*="button" i]'));
            
            const validCandidates = candidates.filter(el => {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return false;
                
                if (el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled')) return false;
                
                return getScore(el) > 0;
            });

            if (validCandidates.length > 0) {
                validCandidates.sort((a, b) => getScore(b) - getScore(a));
                const best = validCandidates[0];
                best.click();
                return true;
            }
            return false;
        }
        """
        try:
            clicked = await page.evaluate(js_click_script)
            if clicked:
                logger.debug("Successfully clicked submit/apply button via JS evaluator.")
                return True
        except Exception as e:
            logger.debug(f"JS submit click failed: {e}")

        # Fallback to standard Playwright selectors
        submit_selectors = [
            ApplyFlowSelectors.SUBMIT_BUTTON,
            ApplyFlowSelectors.NEXT_BUTTON,
            ApplyFlowSelectors.GENERIC_SUBMIT,
            ApplyFlowSelectors.GENERIC_APPLY,
            ApplyFlowSelectors.GENERIC_SUBMIT_TYPE,
            'input[type="submit"]',
            'input[type="button"][value*="Submit" i]',
            'input[type="button"][value*="Apply" i]',
        ]

        for selector in submit_selectors:
            clicked = await self._interactions.safe_click(selector, timeout=2000)
            if clicked:
                logger.debug(f"Clicked submit with fallback selector: {selector}")
                return True

        return False

    async def check_application_failure(self) -> str | None:
        """Check if the application failed with an explicit error/warning on the page."""
        page = self._engine.page
        try:
            failure_text = await page.evaluate(
                """
                () => {
                    const phrases = [
                        "application was not accepted",
                        "please answer all mandatory questions",
                        "please answer the mandatory questions",
                        "incomplete information",
                        "reapplying",
                        "answer mandatory",
                        "required field",
                        "fill all mandatory",
                    ];
                    const errorSelectors = [
                        '[class*="error" i]', '[class*="alert" i]', '[class*="toast" i]',
                        '[class*="warning" i]', '[class*="validation" i]', '[role="alert"]',
                        '[class*="apply" i]', '[class*="modal" i]', '[class*="screening" i]',
                        '[class*="chatbot" i]', '[class*="chat" i]',
                    ];
                    const snippets = [];
                    for (const sel of errorSelectors) {
                        document.querySelectorAll(sel).forEach(el => {
                            const style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden') return;
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) return;
                            const text = (el.innerText || el.textContent || "").trim();
                            if (text && text.length < 500) snippets.push(text.toLowerCase());
                        });
                    }
                    for (const text of snippets) {
                        for (const phrase of phrases) {
                            if (text.includes(phrase)) return phrase;
                        }
                    }
                    return null;
                }
                """
            )
            if failure_text:
                if "mandatory" in failure_text or "incomplete" in failure_text or "required" in failure_text:
                    return "Incomplete information / unanswered mandatory questions"
                return f"Application rejected: {failure_text}"
        except PlaywrightError:
            pass
        return None

    async def check_application_success(self) -> bool:
        """Check if the application was submitted successfully."""
        page = self._engine.page

        # Check for success indicators via selectors
        success_selectors = [
            ApplyFlowSelectors.APPLICATION_SUCCESS,
            '//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "applied successfully")]',
            '//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "successfully applied")]',
            ApplyFlowSelectors.SUCCESS_SUBMITTED,
            ApplyFlowSelectors.SUCCESS_RECEIVED,
            '//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "applied") and not(contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "apply "))]',
        ]

        for selector in success_selectors:
            if await self._interactions.element_exists(selector):
                return True

        # Check page content for success messages
        try:
            body_text = await page.evaluate("document.body.innerText")
            success_phrases = [
                "applied successfully",
                "application submitted",
                "already applied",
                "application received",
                "successfully applied",
                "thank you for applying",
                "application sent",
                "your application has been sent",
            ]
            for phrase in success_phrases:
                if phrase in body_text.lower():
                    return True
        except PlaywrightError:
            pass

        return False

    async def get_external_apply_url(self) -> str | None:
        """
        Extract the external apply URL without marking the job as applied.
        Uses an unauthenticated browser context to click or resolve the link.
        """
        page = self._engine.page
        href = None

        try:
            # 1. Try to extract URL directly from DOM first
            element = await page.query_selector(JobDetailSelectors.EXTERNAL_APPLY)
            if element:
                href = await element.get_attribute("href")
                if not href:
                    # Check if the parent is an anchor tag safely within JS to avoid null reference errors
                    parent_tag = await element.evaluate(
                        "el => el.parentElement ? el.parentElement.tagName.toLowerCase() : null"
                    )
                    if parent_tag == "a":
                        href = await element.evaluate("el => el.parentElement.getAttribute('href')")

            # 2. Use an unauthenticated context to resolve the true company URL safely
            browser = getattr(self._engine, "_browser", None)
            if browser:
                new_context = await browser.new_context()
                new_page = await new_context.new_page()
                try:
                    if href and href.startswith("http"):
                        # Resolve the tracking link
                        await new_page.goto(href, wait_until="domcontentloaded", timeout=15000)
                        final_url = new_page.url
                        if (
                            "naukri.com/nlogin" not in final_url
                            and "naukri.com/myapply" not in final_url
                        ):
                            return final_url
                        return href  # Fallback to the original href
                    else:
                        # No href found in DOM, we must click it in the unauthenticated context
                        job_url = page.url
                        await new_page.goto(job_url, wait_until="domcontentloaded", timeout=15000)

                        # Click the apply button and capture the new tab
                        async with new_context.expect_page(timeout=10000) as new_tab_info:
                            # Use evaluate to click to avoid strict visibility checks blocking it.
                            # We iterate over buttons and links to find the one with the correct text,
                            # which perfectly handles deeply nested spans and SVG icons inside the button.
                            await new_page.evaluate(
                                """
                                () => {
                                    const elements = [...document.querySelectorAll('button, a, [role="button"]')];
                                    const externalBtn = elements.find(el => {
                                        const text = (el.innerText || '').toLowerCase().replace(/\\s+/g, ' ');
                                        return text.includes('apply on company');
                                    });
                                    if (externalBtn) {
                                        externalBtn.click();
                                    }
                                }
                            """
                            )

                        new_tab = await new_tab_info.value
                        await new_tab.wait_for_load_state("domcontentloaded", timeout=10000)
                        final_url = new_tab.url
                        await new_tab.close()

                        if (
                            "naukri.com/nlogin" not in final_url
                            and "naukri.com/myapply" not in final_url
                        ):
                            return final_url
                except Exception as e:
                    logger.debug(f"Unauthenticated context extraction failed: {e}")
                finally:
                    await new_context.close()

            return href

        except (PlaywrightTimeoutError, PlaywrightError) as e:
            logger.warning(f"Failed to extract external URL: {e}")
            return None
