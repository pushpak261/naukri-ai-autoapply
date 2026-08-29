"""
JobDetailPage Page Object for Naukri.com.
Encapsulates parsing job details, detecting screening forms, answering questions, and submitting applications.
"""

from __future__ import annotations

import asyncio
import json

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.config.constants import (
    ELEMENT_TIMEOUT,
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
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await self._interactions.wait_for_navigation_complete()
        await asyncio.sleep(2)

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
                if any(x in text for x in ["applied", "already applied", "submitted", "received"]):
                    return True
        except PlaywrightError:
            pass

        return False

    async def is_external_apply(self) -> bool:
        """Check if the job apply button redirects to an external site."""
        return await self._interactions.element_exists(JobDetailSelectors.EXTERNAL_APPLY)

    async def click_external_apply_button(self) -> bool:
        """Click the external apply button to navigate to the company site."""
        return await self._interactions.safe_click(JobDetailSelectors.EXTERNAL_APPLY, timeout=5000)

    async def is_external_apply_successful(self) -> bool:
        """Check if the external apply page shows a success/confirmation."""
        page = self._engine.page
        try:
            text = await page.inner_text("body") or ""
            text_lower = text.lower()
            if any(x in text_lower for x in ["application submitted", "thank you", "we received", "successfully applied"]):
                return True
        except Exception:
            pass
        return False

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
                            if (text === 'apply' || text === 'apply now' || (text.startsWith('apply') && !text.includes('application') && !text.includes('applicant') && !text.includes('applying')) || text.includes('walk-in') || text.includes('walkin') || text === 'interested') {
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
        if await self._interactions.element_exists(
            '[class*="chatbot-container"], [class*="bot-msg"], [class*="chatbot-msg"], '
            '[class*="nI-chatbot"], [class*="chatbot_"], [class*="bot-body"], '
            '[class*="chat-body"], [class*="screening-bot"], [class*="screening_bot"], '
            '[class*="apply-chat"], [class*="chat-panel"]'
        ):
            return True
        # Fallback: check for chatbot pattern (bot messages + text input + Save button)
        try:
            page = self._engine.page
            return await page.evaluate(
                r"""() => {
                    // Look for a panel that has both bot messages and a text input + Save button
                    const panels = document.querySelectorAll(
                        '[class*="chat" i], [class*="bot" i], [class*="screening" i], ' +
                        '[class*="apply" i], [class*="modal" i], [class*="dialog" i]'
                    );
                    for (const panel of panels) {
                        const style = window.getComputedStyle(panel);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        const text = panel.innerText || '';
                        const hasInput = panel.querySelector('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea');
                        const hasSaveBtn = Array.from(panel.querySelectorAll('button, [role="button"], a')).some(
                            b => (b.textContent || '').trim().toLowerCase().includes('save')
                        );
                        // Bot questions typically contain ? and are conversational
                        const lines = text.split('\\n').filter(l => l.trim().length > 0);
                        const questionLines = lines.filter(l => l.includes('?')).length;
                        if (hasInput && hasSaveBtn && (questionLines >= 1 || text.toLowerCase().includes('question'))) {
                            return true;
                        }
                    }
                    return false;
                }"""
            )
        except Exception:
            return False

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

        # Check using our robust extraction script
        questions = await self.extract_screening_questions()
        return len(questions) > 0

    async def extract_screening_questions(self) -> list[dict]:
        """
        Extract screening questions from the current apply form using a robust JS-based DOM engine.
        Generates stable selectors that survive re-renders (CSS path, element fingerprints).

        Returns:
            List of dicts with question text, type, options, stable selectors, and current value.
        """
        page = self._engine.page
        try:
            js_script = r"""
            () => {
                // ---- CSS.escape polyfill ----
                if (!CSS.escape) {
                    CSS.escape = function(value) {
                        if (typeof value !== 'string') return '';
                        var result = '';
                        for (var i = 0; i < value.length; i++) {
                            var ch = value.charAt(i);
                            if (ch === '\\') result += '\\\\';
                            else if (/[ !"#$%&'()*+,./:;<=>?@\[\]^`{|}~]/.test(ch) || ch.charCodeAt(0) <= 0x1f) {
                                result += '\\' + ch.charCodeAt(0).toString(16) + ' ';
                            } else result += ch;
                        }
                        return result;
                    };
                }

                // ---- Helpers ----

                function isVisible(el) {
                    if (!el || !el.getBoundingClientRect) return false;
                    try {
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return false;

                        const type = (el.getAttribute('type') || '').toLowerCase();
                        if (type === 'radio' || type === 'checkbox') {
                            const parentLabel = el.closest('label');
                            if (parentLabel) {
                                const pStyle = window.getComputedStyle(parentLabel);
                                if (pStyle.display !== 'none' && pStyle.visibility !== 'hidden') {
                                    const pRect = parentLabel.getBoundingClientRect();
                                    if (pRect.width > 0 && pRect.height > 0) return true;
                                }
                            }
                            if (el.id) {
                                const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                                if (label) {
                                    const lStyle = window.getComputedStyle(label);
                                    if (lStyle.display !== 'none' && lStyle.visibility !== 'hidden') {
                                        const lRect = label.getBoundingClientRect();
                                        if (lRect.width > 0 && lRect.height > 0) return true;
                                    }
                                }
                            }
                        }

                        if (style.opacity === '0' || parseFloat(style.opacity) < 0.1) return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    } catch(e) { return false; }
                }

                function cleanQuestionText(text) {
                    if (!text) return "";
                    let cleaned = text.trim();
                    cleaned = cleaned.replace(/[\*:\s]+$/, "");
                    cleaned = cleaned.replace(/^\s*[\*:\s]+/, "");
                    cleaned = cleaned.replace(/\((required|mandatory|optional|must answer|choose)\)/gi, "");
                    cleaned = cleaned.trim();

                    if (!cleaned) return "";

                    // === EXCLUDE raw DOM element IDs or internal attribute strings ===
                    if (/^(userinput|inputbox|agent_|qsb|select_|option_)/i.test(cleaned) || /__\w+/.test(cleaned)) {
                        return "";
                    }

                    // === EXCLUDE system/error/success messages posing as questions ===
                    const lower = cleaned.toLowerCase();
                    const skipPatterns = [
                        'oops', 'not accepted', 'incomplete information',
                        'reapplying', 'already applied', 'applied successfully',
                        'successfully applied', 'application submitted',
                        'thank you for applying', 'we have received',
                        'your application has been', 'please answer all mandatory',
                        'please fill', 'click here to highlight',
                        'want callbacks', 'increase your chances',
                        'upload resume', 'attach resume',
                        'deselect resume', 'remove resume',
                        'error', 'warning', 'alert',
                    ];
                    for (const pat of skipPatterns) {
                        if (lower.includes(pat)) return "";
                    }
                    // Skip very long text that is likely a description, not a question
                    if (cleaned.length > 250) return "";

                    return cleaned;
                }

                function findSharedAncestor(elements) {
                    if (elements.length === 0) return null;
                    if (elements.length === 1) return elements[0].parentElement;
                    let ancestor = elements[0].parentElement;
                    while (ancestor) {
                        if (elements.every(el => ancestor.contains(el))) return ancestor;
                        ancestor = ancestor.parentElement;
                    }
                    return document.body;
                }

                function getCleanedTextExcluding(element, excludeElements) {
                    let text = "";
                    for (let node of element.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            text += node.textContent;
                        } else if (node.nodeType === Node.ELEMENT_NODE) {
                            if (excludeElements.some(ex => ex === node || ex.contains(node))) continue;
                            text += " " + getCleanedTextExcluding(node, excludeElements);
                        }
                    }
                    return text;
                }

                // Generate a stable CSS selector for an element that survives re-renders
                function generateStableSelector(el) {
                    if (!el || el === document.body || el === document.documentElement) return '';
                    // Prefer id
                    if (el.id) return '#' + CSS.escape(el.id);
                    // Build from tag + attributes
                    const tag = el.tagName.toLowerCase();
                    const attrs = [];
                    const name = el.getAttribute('name');
                    const type = el.getAttribute('type');
                    const placeholder = el.getAttribute('placeholder');
                    const ariaLabel = el.getAttribute('aria-label');
                    const className = el.getAttribute('class');
                    if (name) attrs.push('[name="' + CSS.escape(name) + '"]');
                    if (type) attrs.push('[type="' + type + '"]');
                    if (placeholder) attrs.push('[placeholder="' + CSS.escape(placeholder) + '"]');
                    if (ariaLabel) attrs.push('[aria-label="' + CSS.escape(ariaLabel) + '"]');

                    // Build a path as fallback
                    let path = tag + attrs.join('');
                    // Check uniqueness; if not unique, prepend parent path
                    let matches = document.querySelectorAll(path);
                    if (matches.length > 1) {
                        // Try with nth-of-type
                        let parent = el.parentElement;
                        let parentPath = '';
                        if (parent && parent !== document.body) {
                            parentPath = generateStableSelector(parent);
                            let candidate = parentPath + ' > ' + path;
                            let parentMatches = document.querySelectorAll(candidate);
                            if (parentMatches.length === 1) return candidate;
                        }
                        // Use n-th child approach
                        let childIndex = 1;
                        let sibling = el.previousElementSibling;
                        while (sibling) { childIndex++; sibling = sibling.previousElementSibling; }
                        path = tag + ':nth-of-type(' + childIndex + ')' + attrs.join('');
                    }
                    return path;
                }

                function getLabelForGroup(elements, formContainer) {
                    if (elements.length === 0) return "";
                    const first = elements[0];

                    const isFiller = (t) => {
                        if (!t) return true;
                        const l = t.toLowerCase().trim();
                        if (/^(userinput|inputbox|agent_|qsb|select_|option_)/i.test(l) || /__\w+/.test(l)) return true;
                        return /type message|type answer|enter answer|type here|enter text|write message|write answer|input message/i.test(l);
                    };

                    // 0. Chatbot message bubble lookup if inside chatbot/modal/drawer container
                    const chatbotBox = first.closest ? first.closest('[class*="bot" i], [class*="chat" i], [class*="drawer" i], [class*="dialog" i], [class*="modal" i]') : null;
                    if (chatbotBox) {
                        const botBubbles = Array.from(chatbotBox.querySelectorAll(
                            '[class*="bot-msg" i], [class*="botMsg" i], [class*="recruiter" i], ' +
                            '[class*="chat-msg" i], [class*="msg" i], [class*="bubble" i], p, span, div'
                        )).filter(el => {
                            if (el.contains(first) || !isVisible(el)) return false;
                            const userClass = '[class*="user" i], [class*="candidate" i], [class*="reply" i], [class*="sent" i], [class*="input" i], [class*="right" i], [class*="answer" i], [class*="response" i], [class*="user_msg" i], [class*="user-msg" i], [class*="userMsg" i]';
                            if (el.closest(userClass)) return false;
                            const t = (el.innerText || el.textContent || '').trim();
                            if (!t || isFiller(t) || t.length < 4 || t.length > 300) return false;
                            if (/^(save|submit|next|cancel|close|thank you|1 year|1 years|1|yes|no|immediate|pune|4\.4|4\.5|6 lpa)$/i.test(t)) return false;
                            try {
                                const st = window.getComputedStyle(el);
                                if (st.textAlign === 'right' || st.justifyContent === 'flex-end' || st.alignSelf === 'flex-end' || st.float === 'right') return false;
                            } catch(e) {}
                            return true;
                        });

                        const questionBubbles = botBubbles.filter(el => {
                            const t = (el.innerText || el.textContent || '').trim();
                            // Questions may or may not have ? marks (e.g. "Enter your expected CTC")
                            return t.includes('?')
                                || /how many|years|experience|exp|notice|ctc|salary|skill|location|resid|relocat|qualification|degree|rate|level|proficiency|availability|joining|start|date|birth|language|portfolio|github|linkedin|phone|mobile|number|contact|strength|weakness|achievement|project|describe|reason|change|why|describe/gi.test(t);
                        });

                        if (questionBubbles.length > 0) {
                            const activeQ = questionBubbles[questionBubbles.length - 1];
                            const txt = (activeQ.innerText || activeQ.textContent || '').trim();
                            if (txt) return txt;
                        }
                    }

                    // 1. Explicit label[for]
                    if (first.id) {
                        const label = document.querySelector('label[for="' + CSS.escape(first.id) + '"]');
                        if (label && isVisible(label)) {
                            const text = label.innerText.trim();
                            if (text.length > 2 && !isFiller(text)) return text;
                        }
                    }

                    // 2. Inside label tag
                    const parentLabel = first.closest ? first.closest('label') : null;
                    if (parentLabel && isVisible(parentLabel)) {
                        const text = parentLabel.innerText.trim();
                        if (text.length > 2 && !isFiller(text)) return text;
                    }

                    // 3. Shared ancestor
                    let ancestor = findSharedAncestor(elements);
                    if (formContainer && formContainer.contains(ancestor) && ancestor !== formContainer) {
                        const optionLabelsAndInputs = [];
                        elements.forEach(el => {
                            optionLabelsAndInputs.push(el);
                            const parentLbl = el.closest ? el.closest('label') : null;
                            if (parentLbl) optionLabelsAndInputs.push(parentLbl);
                        });
                        const ancestorText = getCleanedTextExcluding(ancestor, optionLabelsAndInputs).trim();
                        if (ancestorText.length > 3 && !isFiller(ancestorText)) return ancestorText;
                    }

                    // 4. Preceding sibling text
                    let prev = first.previousElementSibling;
                    while (prev) {
                        if (isVisible(prev)) {
                            const text = prev.innerText || prev.textContent || "";
                            if (text.trim().length > 3 && !isFiller(text.trim())) return text.trim();
                        }
                        prev = prev.previousElementSibling;
                    }

                    // 5. Parent container heading/label text
                    if (first.parentElement) {
                        let walker = first.parentElement;
                        for (let i = 0; i < 3 && walker; i++) {
                            const heading = walker.querySelector('h1, h2, h3, h4, h5, h6, strong, b, label:not(:has(input)), span:not(:has(input))');
                            if (heading && isVisible(heading)) {
                                const ht = heading.innerText.trim();
                                if (ht.length > 3 && ht.length < 200 && !isFiller(ht)) return ht;
                            }
                            walker = walker.parentElement;
                        }
                    }

                    // 6. Attributes (skipping filler placeholders)
                    const placeholder = first.getAttribute ? first.getAttribute('placeholder') : '';
                    if (placeholder && placeholder.length > 2 && !isFiller(placeholder)) return placeholder;
                    const name = first.getAttribute ? first.getAttribute('name') : '';
                    if (name && name.length > 2 && !isFiller(name)) return name;
                    const ariaLabel = first.getAttribute ? first.getAttribute('aria-label') : '';
                    if (ariaLabel && ariaLabel.length > 2 && !isFiller(ariaLabel)) return ariaLabel;

                    return "";
                }

                // Build element fingerprint for matching across re-renders
                function elementFingerprint(el) {
                    const tag = el.tagName.toLowerCase();
                    const type = (el.getAttribute('type') || '').toLowerCase();
                    const name = el.getAttribute('name') || '';
                    const id = el.id || '';
                    const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                    const className = (el.className || '').toString().toLowerCase().replace(/\\s+/g, ' ').trim();
                    // Get the label text if available
                    let labelText = '';
                    const label = el.closest('label') || (id ? document.querySelector('label[for="' + CSS.escape(id) + '"]') : null);
                    if (label) labelText = (label.innerText || '').trim().toLowerCase();
                    // Get surrounding question text (first 60 chars)
                    const parentText = (el.parentElement ? (el.parentElement.innerText || '').trim().toLowerCase() : '');
                    const surrounding = parentText.replace(/\\s+/g, ' ').substring(0, 120);
                    return JSON.stringify({
                        tag: tag, type: type, name: name, id: id,
                        placeholder: placeholder.substring(0, 50),
                        ariaLabel: ariaLabel.substring(0, 50),
                        class: className.substring(0, 100),
                        labelText: labelText.substring(0, 80),
                        surrounding: surrounding
                    });
                }

                // Find element by its fingerprint (after re-render)
                function findElementByFingerprint(fp) {
                    if (!fp) return null;
                    try { fp = JSON.parse(fp); } catch(e) { return null; }
                    const candidates = Array.from(document.querySelectorAll(
                        'input' + (fp.type ? '[type="' + fp.type + '"]' : '') +
                        ', select, textarea, [contenteditable="true"], [role="switch"], [role="checkbox"]'
                    )).filter(el => {
                        try {
                            if (!isVisible(el)) return false;
                            const hType = (el.getAttribute('type') || '').toLowerCase();
                            if (['hidden', 'submit', 'button', 'image', 'file'].includes(hType)) return false;
                            const tag = el.tagName.toLowerCase();
                            if (fp.tag && fp.tag !== tag) return false;
                            if (fp.name && el.getAttribute('name') !== fp.name) return false;
                            if (fp.id && el.id !== fp.id) return false;
                            if (fp.placeholder && fp.placeholder.length > 3) {
                                const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                                if (ph !== fp.placeholder && !ph.includes(fp.placeholder) && !fp.placeholder.includes(ph)) {
                                    // placeholder mismatch - not strict
                                }
                            }
                            return true;
                        } catch(e) { return false; }
                    });
                    if (candidates.length === 1) return candidates[0];
                    // Try additional matching by surrounding text
                    if (fp.surrounding && fp.surrounding.length > 20) {
                        for (const c of candidates) {
                            const ctx = (c.parentElement ? (c.parentElement.innerText || '').trim().toLowerCase() : '');
                            const ctxNorm = ctx.replace(/\\s+/g, ' ').substring(0, 120);
                            if (ctxNorm === fp.surrounding) return c;
                        }
                    }
                    return candidates.length > 0 ? candidates[0] : null;
                }

                // ---- Main extraction ----

                // Identify form container
                const containerSelectors = [
                    '[class*="apply-modal"]', '[class*="apply-form"]',
                    '[class*="chatbot"]', '[class*="chat" i]', '[class*="bot" i]',
                    '[class*="modal" i]', '[class*="popup" i]', '[class*="dialog" i]',
                    'form[class*="apply"]', '[class*="screening"]', 'form', 'body'
                ];
                let formContainer = null;
                for (let sel of containerSelectors) {
                    const elements = document.querySelectorAll(sel);
                    for (let el of elements) {
                        if (isVisible(el) && el.querySelector('input:not([type="hidden"]), select, textarea, [contenteditable="true"]')) {
                            formContainer = el;
                            break;
                        }
                    }
                    if (formContainer && formContainer.tagName !== 'BODY') break;
                }
                if (!formContainer) formContainer = document.body;

                // Collect ALL visible interactive elements
                let allControls = Array.from(formContainer.querySelectorAll(
                    'input, select, textarea, [contenteditable="true"], [role="switch"], [role="checkbox"]:not(input)'
                ));
                let visibleControls = allControls.filter(el => {
                    if (!isVisible(el)) return false;
                    const type = (el.getAttribute('type') || '').toLowerCase();
                    if (['hidden', 'submit', 'button', 'image', 'file'].includes(type)) return false;
                    if (el.closest('header, nav, [class*="header" i], [class*="nav" i], [class*="qsb" i], [class*="search-bar" i], [class*="searchBar" i]')) return false;
                    return true;
                });

                if (visibleControls.length === 0 && formContainer !== document.body) {
                    formContainer = document.body;
                    allControls = Array.from(formContainer.querySelectorAll(
                        'input, select, textarea, [contenteditable="true"], [role="switch"], [role="checkbox"]:not(input)'
                    ));
                    visibleControls = allControls.filter(el => {
                        if (!isVisible(el)) return false;
                        const type = (el.getAttribute('type') || '').toLowerCase();
                        if (['hidden', 'submit', 'button', 'image', 'file'].includes(type)) return false;
                        if (el.closest('header, nav, [class*="header" i], [class*="nav" i], [class*="qsb" i], [class*="search-bar" i], [class*="searchBar" i]')) return false;
                        return true;
                    });
                }

                // ---- Detect toggle/switch elements (styled as switches, not standard input) ----
                // Use simple selectors + JS visibility filter (NO :visible/:hidden which are jQuery-only)
                const rawToggleCandidates = Array.from(formContainer.querySelectorAll(
                    '[role="switch"], [class*="toggle" i], [class*="switch" i]'
                )).filter(el => {
                    // Skip standard form controls
                    const tag = el.tagName.toLowerCase();
                    if (tag === 'input' || tag === 'select' || tag === 'textarea') return false;
                    return isVisible(el);
                });

                // Find labels containing hidden/opacity-zero checkboxes by iterating JS
                const allLabels = Array.from(formContainer.querySelectorAll('label')).filter(isVisible);
                const styledCheckboxLabels = allLabels.filter(lbl => {
                    const cb = lbl.querySelector('input[type="checkbox"]');
                    if (!cb) return false;
                    try {
                        const style = window.getComputedStyle(cb);
                        if (style.display === 'none' || style.visibility === 'hidden') return true;
                        if (parseFloat(style.opacity) < 0.1) return true;
                        const rect = cb.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return true;
                    } catch(e) { /* ignore */ }
                    return false;
                });

                // Combine toggle candidates
                const toggleCandidates = rawToggleCandidates.concat(styledCheckboxLabels);

                for (const toggle of toggleCandidates) {
                    // Check if toggle is already represented by a visible checkbox input
                    const innerCheckbox = toggle.querySelector('input[type="checkbox"]');
                    if (innerCheckbox && visibleControls.includes(innerCheckbox)) continue;

                    // It's a custom toggle - synthesize a question
                    const label = toggle.querySelector('label') || toggle;
                    const qText = (label.innerText || label.textContent || '').trim();
                    if (qText && qText.length > 3) {
                        const isChecked = toggle.getAttribute('aria-checked') === 'true' ||
                            toggle.classList.contains('active') ||
                            toggle.classList.contains('on') ||
                            (innerCheckbox && innerCheckbox.checked);
                        const stableSel = generateStableSelector(toggle);
                        visibleControls.push({
                            tagName: 'DIV',
                            getAttribute: function(a) {
                                if (a === 'type') return 'checkbox';
                                if (a === 'name') return toggle.getAttribute('name') || '';
                                if (a === 'id') return toggle.id || '';
                                if (a === 'aria-label') return qText;
                                if (a === 'placeholder') return '';
                                if (a === 'required') return toggle.hasAttribute('aria-required') || qText.includes('*');
                                if (a === 'aria-required') return toggle.getAttribute('aria-required');
                                return toggle.getAttribute(a);
                            },
                            hasAttribute: function(a) {
                                if (a === 'required') return toggle.hasAttribute('aria-required') || qText.includes('*');
                                return toggle.hasAttribute(a);
                            },
                            __isToggle: true,
                            __toggleEl: toggle,
                            __stableSelector: stableSel,
                            __qText: qText,
                            __checked: isChecked,
                            closest: function(s) { return toggle.closest ? toggle.closest(s) : null; },
                            parentElement: toggle.parentElement,
                            value: isChecked ? 'Yes' : '',
                            checked: isChecked,
                            __actualCheckbox: innerCheckbox
                        });
                    }
                }

                // Group controls by name + type for radio/checkbox, individually for others
                const groups = [];
                const processedNames = new Set();

                visibleControls.forEach(control => {
                    const tagName = control.tagName ? control.tagName.toLowerCase() : 'div';
                    const typeAttr = (control.getAttribute('type') || '').toLowerCase();
                    const name = control.getAttribute('name') || '';

                    if ((typeAttr === 'radio' || typeAttr === 'checkbox') && name) {
                        if (processedNames.has(name)) return;
                        processedNames.add(name);
                        const groupInputs = visibleControls.filter(el => {
                            const elType = (el.getAttribute('type') || '').toLowerCase();
                            return elType === typeAttr && el.getAttribute('name') === name;
                        });
                        groups.push({ type: typeAttr, name: name, elements: groupInputs });
                    } else {
                        let detectedType = typeAttr || 'text';
                        if (tagName === 'select') detectedType = 'dropdown';
                        else if (tagName === 'textarea') detectedType = 'text_area';
                        else if (control.__isToggle) detectedType = 'checkbox';
                        groups.push({ type: detectedType, name: name, elements: [control] });
                    }
                });

                // Process each group
                const questions = [];
                groups.forEach((group, index) => {
                    const fieldId = 'agent_q_' + index;
                    const rawQuestion = getLabelForGroup(group.elements, formContainer);
                    const cleanedQuestion = cleanQuestionText(rawQuestion) || group.elements[0].__qText || '';

                    let required = false;
                    group.elements.forEach(el => {
                        if (el.hasAttribute && (el.hasAttribute('required') || el.getAttribute('aria-required') === 'true')) {
                            required = true;
                        }
                    });
                    if (rawQuestion.includes('*') || /required|mandatory|must\s*answer/i.test(rawQuestion)) {
                        required = true;
                    }

                    let options = [];
                    let value = "";
                    const firstEl = group.elements[0];
                    let stableSelector = '';

                    if (group.type === 'dropdown') {
                        const el = firstEl;
                        el.setAttribute('data-agent-field-id', fieldId);
                        stableSelector = generateStableSelector(el);
                        value = el.value || "";
                        el.querySelectorAll('option').forEach(opt => {
                            const optText = opt.textContent.trim();
                            if (optText && !/select|choose|--/i.test(optText)) {
                                options.push({ text: optText, value: opt.value });
                            }
                        });
                    } else if (group.type === 'radio' || group.type === 'checkbox') {
                        group.elements.forEach((el, optIdx) => {
                            const optFieldId = fieldId + '_opt_' + optIdx;
                            el.setAttribute('data-agent-field-id', optFieldId);
                            const optStableSel = el.__stableSelector || generateStableSelector(el);

                            let optText = "";
                            if (el.__qText) {
                                optText = el.__qText;
                            } else {
                                const parentLabel = el.closest ? el.closest('label') : null;
                                if (parentLabel) {
                                    optText = parentLabel.innerText.trim();
                                } else if (el.id) {
                                    const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                                    if (label) optText = label.innerText.trim();
                                }
                            }
                            if (!optText) optText = el.value || "";

                            if (el.checked || el.__checked) value = optText;

                            options.push({
                                text: optText,
                                value: el.value || optText,
                                selector: "[data-agent-field-id='" + optFieldId + "']",
                                stableSelector: optStableSel,
                                elementFingerprint: elementFingerprint(el)
                            });
                        });
                        stableSelector = options.length > 0 ? options[0].stableSelector : '';
                    } else {
                        const el = firstEl;
                        el.setAttribute('data-agent-field-id', fieldId);
                        stableSelector = generateStableSelector(el);
                        value = el.value !== undefined ? el.value : (el.innerText || el.textContent || "");

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

                    let finalQuestionText = cleanedQuestion;
                    if (!finalQuestionText || finalQuestionText.length < 3) {
                        const el0 = group.elements[0];
                        // Smarter inference chain:
                        // 1. aria-label
                        let inferred = el0.getAttribute ? (el0.getAttribute('aria-label') || '').trim() : '';
                        // 2. placeholder
                        if (!inferred || inferred.length < 3) {
                            inferred = el0.getAttribute ? (el0.getAttribute('placeholder') || '').trim() : '';
                        }
                        // 3. name attribute (convert camelCase/snake_case to words)
                        if (!inferred || inferred.length < 3) {
                            const nameAttr = el0.getAttribute ? (el0.getAttribute('name') || '') : '';
                            if (nameAttr) {
                                inferred = nameAttr
                                    .replace(/_/g, ' ')
                                    .replace(/([A-Z])/g, ' $1')
                                    .replace(/(\d+)/g, ' $1')
                                    .trim()
                                    .toLowerCase();
                            }
                        }
                        // 4. parent container text (up to 3 levels)
                        if (!inferred || inferred.length < 3) {
                            let walker = el0.parentElement;
                            for (let i = 0; i < 3 && walker; i++) {
                                const siblings = Array.from(walker.children).filter(c =>
                                    c !== el0 && c.tagName !== 'INPUT' && c.tagName !== 'SELECT' && c.tagName !== 'TEXTAREA'
                                );
                                for (const sib of siblings) {
                                    const st = (sib.innerText || '').trim();
                                    if (st && st.length > 3 && st.length < 200) {
                                        inferred = st;
                                        break;
                                    }
                                }
                                if (inferred) break;
                                walker = walker.parentElement;
                            }
                        }
                        // 5. preceding sibling heading/strong text
                        if (!inferred || inferred.length < 3) {
                            let prev = el0.previousElementSibling;
                            while (prev) {
                                const tag = prev.tagName.toLowerCase();
                                if (['h1','h2','h3','h4','h5','h6','strong','b','label','span','div','p'].includes(tag)) {
                                    const pt = (prev.innerText || '').trim();
                                    if (pt && pt.length > 3 && pt.length < 200) {
                                        inferred = pt;
                                        break;
                                    }
                                }
                                prev = prev.previousElementSibling;
                            }
                        }
                        finalQuestionText = cleanQuestionText(inferred) || ('Question ' + (index + 1));
                    }

                    questions.push({
                        id: fieldId,
                        question: finalQuestionText,
                        original_question: rawQuestion || finalQuestionText,
                        type: group.type,
                        options: options,
                        required: required,
                        selector: "[data-agent-field-id='" + fieldId + "']",
                        stableSelector: stableSelector,
                        elementFingerprint: elementFingerprint(firstEl),
                        value: value
                    });
                });

                // Chatbot flow fallback
                if (questions.length === 0) {
                    const chatbotSelectors = '[class*="chatbot-msg"], [class*="bot-msg"], [class*="chat-msg"], [class*="msg-bubble"], [class*="message"]:not([class*="error"]), [class*="bot-text"], [class*="chat-text"], [class*="bot-content"], [class*="question-text"], [class*="screening-question"]';
                    const chatbotMsgs = document.querySelectorAll(chatbotSelectors);
                    if (chatbotMsgs.length > 0) {
                        // Find the last visible message that looks like a question
                        let lastMsg = null;
                        for (let i = chatbotMsgs.length - 1; i >= 0; i--) {
                            const msg = chatbotMsgs[i];
                            try {
                                const style = window.getComputedStyle(msg);
                                if (style.display === 'none' || style.visibility === 'hidden') continue;
                                const rect = msg.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0) continue;
                                lastMsg = msg;
                                break;
                            } catch(e) { continue; }
                        }
                        if (!lastMsg) lastMsg = chatbotMsgs[chatbotMsgs.length - 1];
                        const msgText = (lastMsg.innerText || lastMsg.textContent || "").trim();
                        // Try to find question text even if msgText was cleaned out
                        const rawMsgText = msgText || (lastMsg.parentElement ? (lastMsg.parentElement.innerText || '').trim() : '');
                        if (rawMsgText) {
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
                                            selector: "[data-agent-field-id='" + optFieldId + "']",
                                            stableSelector: generateStableSelector(opt)
                                        });
                                    }
                                });
                            }

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

                            const cleanedQText = cleanQuestionText(rawMsgText);
                            if (cleanedQText) {
                                questions.push({
                                    id: "agent_chat_q",
                                    question: cleanedQText,
                                    original_question: rawMsgText,
                                    type: options.length > 0 ? "radio" : "text",
                                    options: options,
                                    required: true,
                                    selector: chatbotInputSelector || "input:not([type='hidden'])",
                                    stableSelector: chatbotInputSelector,
                                    elementFingerprint: "",
                                    value: ""
                                });
                            }
                        }
                    }
                }

                return JSON.stringify(questions);
            }
            """
            result_json = await page.evaluate(js_script)
            questions = json.loads(result_json)
            logger.info(f"Detected {len(questions)} screening questions")
            return questions
        except Exception as e:
            logger.error(f"Error during JS-based question extraction: {e}")
            return []

    async def fill_answer_by_metadata(self, question: dict, answer: str) -> bool:
        """
        Fill a question answer using precise metadata and selectors assigned during extraction.
        Uses a multi-strategy fallback chain for robustness against DOM re-renders.
        """
        page = self._engine.page
        q_type = question.get("type")
        q_text = question.get("question")
        selector = question.get("selector") or ""
        stable_selector = question.get("stableSelector", "")
        fingerprint = question.get("elementFingerprint", "")
        options = question.get("options", [])

        try:
            # ---- Strategy chain for each type ----
            if q_type == "dropdown":
                return await self._fill_dropdown_multi_strategy(
                    page, question, options, answer, selector, stable_selector, fingerprint
                )
            elif q_type in ("radio", "checkbox"):
                return await self._fill_choice_multi_strategy(
                    page, question, options, answer, q_type == "checkbox"
                )
            else:
                return await self._fill_text_multi_strategy(
                    page, question, answer, selector, stable_selector, fingerprint
                )
        except Exception as e:
            logger.error(f"Failed to fill answer using metadata for '{q_text}': {e}")

        return False

    async def _fill_dropdown_multi_strategy(
        self, page, question: dict, options: list[dict], answer: str,
        selector: str, stable_selector: str, fingerprint: str
    ) -> bool:
        """Multi-strategy dropdown fill."""
        select_elem = None

        # Strategy 1: data-agent-field-id selector
        if selector:
            select_elem = await page.query_selector(selector)

        # Strategy 2: stable CSS selector
        if not select_elem and stable_selector:
            select_elem = await page.query_selector(stable_selector)

        # Strategy 3: fingerprint lookup
        if not select_elem and fingerprint:
            select_elem = await page.evaluate_handle(
                """(fp) => {
                    try {
                        const data = JSON.parse(fp);
                        const candidates = Array.from(document.querySelectorAll('select'));
                        for (const c of candidates) {
                            if (data.name && c.getAttribute('name') === data.name) return c;
                            if (data.id && c.id === data.id) return c;
                        }
                        return null;
                    } catch(e) { return null; }
                }""",
                fingerprint
            )
            if select_elem:
                select_elem = select_elem.as_element()

        # Strategy 4: find any visible select in form
        if not select_elem:
            select_elem = await page.query_selector('select:not([style*="display: none"])')

        if select_elem:
            try:
                is_visible = await select_elem.is_visible()
            except Exception:
                is_visible = False
            if is_visible:
                result = await self._select_dropdown_option_by_metadata(
                    select_elem, options, answer
                )
                if result:
                    return True
                # Fallback: select by visible text matching
                return await self._select_dropdown_option(select_elem, answer) or True
        return False

    async def _fill_choice_multi_strategy(
        self, page, question: dict, options: list[dict], answer: str, is_checkbox: bool
    ) -> bool:
        """Multi-strategy radio/checkbox fill with label text and DOM fallback."""
        q_text = question.get("question", "")

        # Strategy 1: Try metadata-based selection (using data-agent-field-id)
        if await self._select_choice_option_by_metadata(options, answer, is_checkbox):
            return True

        # Strategy 2: Try stable selectors for each option
        for opt in options:
            stable_sel = opt.get("stableSelector", "")
            if stable_sel:
                elem = await page.query_selector(stable_sel)
                if elem:
                    try:
                        parent_label = await elem.evaluate_handle("el => el.closest('label')")
                        label_elem = parent_label.as_element()
                        if label_elem:
                            await label_elem.scroll_into_view_if_needed()
                            await label_elem.click()
                            return True
                        await elem.scroll_into_view_if_needed()
                        await elem.click()
                        return True
                    except Exception:
                        pass

        # Strategy 3: Try by element fingerprint for each option
        for opt in options:
            fp = opt.get("elementFingerprint", "")
            if fp:
                elem = await page.evaluate_handle(
                    """(fp) => {
                        try {
                            const d = JSON.parse(fp);
                            const sel = d.type ? 'input[type="' + d.type + '"]' : 'input';
                            const candidates = Array.from(document.querySelectorAll(sel));
                            for (const c of candidates) {
                                if (d.name && c.getAttribute('name') === d.name) return c;
                                if (d.id && c.id === d.id) return c;
                                // Match by label text
                                if (d.labelText && d.labelText.length > 5) {
                                    const lbl = c.closest('label') || (c.id && document.querySelector('label[for="' + CSS.escape(c.id) + '"]'));
                                    if (lbl && (lbl.innerText || '').trim().toLowerCase() === d.labelText) return c;
                                }
                            }
                            return null;
                        } catch(e) { return null; }
                    }""",
                    fp
                )
                if elem:
                    elem = elem.as_element()
                    if elem:
                        try:
                            await elem.scroll_into_view_if_needed()
                            await elem.click()
                            return True
                        except Exception:
                            pass

        # Strategy 4: Find by label text matching on page
        answer_lower = answer.lower().strip()
        try:
            labels = await page.query_selector_all("label")
            for label in labels:
                try:
                    label_text = (await label.text_content() or "").strip()
                    if not label_text:
                        continue
                    # Check if this label contains the question text
                    if q_text and (q_text.lower() in label_text.lower() or label_text.lower() in q_text.lower()):
                        radio = await label.query_selector('input[type="radio"], input[type="checkbox"]')
                        if radio:
                            await label.scroll_into_view_if_needed()
                            await label.click()
                            return True
                except Exception:
                    pass

            # Strategy 5: Find by answer text in labels
            for label in labels:
                try:
                    label_text = (await label.text_content() or "").strip().lower()
                    if answer_lower == label_text or answer_lower in label_text or label_text in answer_lower:
                        radio = await label.query_selector('input[type="radio"], input[type="checkbox"]')
                        if radio:
                            await label.scroll_into_view_if_needed()
                            await label.click()
                            return True
                except Exception:
                    pass
        except Exception:
            pass

        # Strategy 6: JS direct DOM manipulation for toggles/switches
        if q_text:
            js_result = await page.evaluate(
                """({ qText, answer, isCheckbox }) => {
                    if (!CSS.escape) {
                        CSS.escape = function(value) {
                            if (typeof value !== 'string') return '';
                            var result = '';
                            for (var i = 0; i < value.length; i++) {
                                var ch = value.charAt(i);
                                if (ch === '\\') result += '\\\\';
                            else if (/[ !"#$%&'()*+,./:;<=>?@\\[\\]^`{|}~]/.test(ch) || ch.charCodeAt(0) <= 0x1f) {
                                    result += '\\' + ch.charCodeAt(0).toString(16) + ' ';
                                } else result += ch;
                            }
                            return result;
                        };
                    }
                    const ql = qText.toLowerCase();
                    const al = answer.toLowerCase().trim();
                    const shouldCheck = al === 'yes' || al === 'true' || al === '1' || al === 'y';

                    // Find toggle/switch elements with matching text
                    const toggles = document.querySelectorAll(
                        '[role="switch"], [class*="toggle" i], [class*="switch" i], ' +
                        'label:has(input[type="checkbox"]), label:has(input[type="radio"])'
                    );
                    for (const tg of toggles) {
                        const tText = (tg.innerText || tg.textContent || '').trim().toLowerCase();
                        if (!tText) continue;
                        if (ql && (tText.includes(ql) || ql.includes(tText))) {
                            // Found matching toggle - click it
                            tg.click();
                            return true;
                        }
                    }

                    // Find any visible unchecked checkbox/radio that's still in form
                    if (shouldCheck) {
                        const inputs = document.querySelectorAll(
                            'input[type="checkbox"]:not([style*="display: none"]):not([style*="visibility: hidden"]), ' +
                            'input[type="radio"]:not([style*="display: none"]):not([style*="visibility: hidden"])'
                        );
                        for (const inp of inputs) {
                            if (!inp.checked && inp.offsetParent !== null) {
                                const lbl = inp.closest('label') || (inp.id && document.querySelector('label[for="' + CSS.escape(inp.id) + '"]'));
                                const ctxText = lbl ? (lbl.innerText || '').trim().toLowerCase() : '';
                                if (ql && (ctxText.includes(ql) || ql.includes(ctxText))) {
                                    inp.click();
                                    inp.checked = true;
                                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                                    return true;
                                }
                            }
                        }
                        // Last resort: check first visible unchecked checkbox
                        for (const inp of inputs) {
                            if (!inp.checked && inp.offsetParent !== null) {
                                inp.click();
                                inp.checked = true;
                                inp.dispatchEvent(new Event('change', { bubbles: true }));
                                inp.dispatchEvent(new Event('input', { bubbles: true }));
                                return true;
                            }
                        }
                    }
                    return false;
                }""",
                {"qText": q_text, "answer": answer, "isCheckbox": is_checkbox}
            )
            if js_result:
                return True

        return False

    async def _fill_text_multi_strategy(
        self, page, question: dict, answer: str,
        selector: str, stable_selector: str, fingerprint: str
    ) -> bool:
        """Multi-strategy text/number/date field fill.
        
        After successfully filling in a chatbot flow, automatically triggers
        the Save button so the answer registers and the next question appears.
        """
        q_text = question.get("question", "")
        filled = False

        # Strategy 1: data-agent-field-id selector
        if not filled and selector:
            if await self._fill_single_text_input(page, selector, answer):
                filled = True

        # Strategy 2: stable CSS selector
        if not filled and stable_selector:
            if await self._fill_single_text_input(page, stable_selector, answer):
                filled = True

        # Strategy 3: fingerprint-based re-find
        if not filled and fingerprint:
            elem = await page.evaluate_handle(
                """(fp) => {
                    try {
                        const d = JSON.parse(fp);
                        const sel = d.type && d.type !== 'text'
                            ? 'input[type="' + d.type + '"], textarea'
                            : 'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"]):not([type="file"]), textarea';
                        const candidates = Array.from(document.querySelectorAll(sel));
                        for (const c of candidates) {
                            if (d.name && c.getAttribute('name') === d.name) return c;
                            if (d.id && c.id === d.id) return c;
                            if (d.placeholder && d.placeholder.length > 3) {
                                const ph = (c.getAttribute('placeholder') || '').toLowerCase();
                                if (ph === d.placeholder) return c;
                            }
                        }
                        return null;
                    } catch(e) { return null; }
                }""",
                fingerprint
            )
            if elem:
                elem = elem.as_element()
                if elem:
                    if await self._fill_element_text(page, elem, answer):
                        filled = True

        # Strategy 4: Find by label text
        if not filled and q_text:
            elem = await self._find_input_by_label_text(page, q_text)
            if elem and await self._fill_element_text(page, elem, answer):
                filled = True

        # Strategy 5: Find by placeholder matching
        if not filled and q_text:
            q_lower = q_text.lower()
            try:
                inputs = await page.query_selector_all(
                    'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"]):not([type="file"]), textarea'
                )
                for inp in inputs:
                    try:
                        ph = (await inp.get_attribute("placeholder") or "").lower()
                        if ph and (q_lower in ph or ph in q_lower):
                            if await self._fill_element_text(page, inp, answer):
                                filled = True
                                break
                    except Exception:
                        pass
            except Exception:
                pass

        # Strategy 6: JS direct DOM fill on any visible unfilled input
        if not filled and q_text:
            js_result = await page.evaluate(
                """({ answer }) => {
                    const inputs = document.querySelectorAll(
                        'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"]):not([type="file"]):not([style*="display: none"]):not([style*="visibility: hidden"]), ' +
                        'textarea:not([style*="display: none"]):not([style*="visibility: hidden"])'
                    );
                    for (const inp of inputs) {
                        if (inp.offsetParent === null) continue;
                        const val = (inp.value || '').trim();
                        if (val === '' || val === 'Select' || val === '--Select--') {
                            inp.focus();
                            const nativeSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            ).set;
                            nativeSetter.call(inp, '');
                            nativeSetter.call(inp, answer);
                            inp.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.blur();
                            inp.dispatchEvent(new Event('blur', { bubbles: true }));
                            return true;
                        }
                    }
                    return false;
                }""",
                {"answer": answer}
            )
            if js_result:
                filled = True

        # After successful fill in chatbot flow, trigger Save button so the
        # answer registers and the next question appears.
        if filled and await self.is_chatbot_flow():
            await asyncio.sleep(0.3)
            try:
                await self.click_chatbot_save_button()
            except Exception:
                pass

        return filled

    async def _fill_single_text_input(self, page, selector: str, answer: str) -> bool:
        """Try to fill a single text input using the given selector."""
        try:
            elem = await page.query_selector(selector)
            if not elem:
                return False
            return await self._fill_element_text(page, elem, answer)
        except Exception:
            return False

    async def _fill_element_text(self, page, element, answer: str) -> bool:
        """Fill text into an element with robust visibility/scroll handling.
        
        Strategy:
        1. For visible elements: Playwright fill() (triggers React/Angular change detection)
        2. For non-visible elements: JS native value setter + all events (focus/input/change/blur)
        3. Always blur + wait for framework reactivity
        4. Verify value was accepted by framework (re-read after reactivity delay)
        """
        try:
            is_visible = await element.is_visible()
        except Exception:
            is_visible = False

        expected_val = answer.strip()

        def verify_fill(elem):
            """Verify the framework accepted the value by re-reading it."""
            async def _inner():
                try:
                    actual = await elem.evaluate("el => el.value || ''")
                    return actual.strip() == expected_val
                except Exception:
                    return False
            return _inner()

        # ---- VISIBLE ELEMENT: use Playwright fill() (handles React change detection) ----
        if is_visible:
            try:
                await element.scroll_into_view_if_needed()
                await element.focus()
                await element.fill("")
                await element.type(answer, delay=20)
                # Blur and wait for framework validation to propagate
                await element.evaluate("el => el.blur()")
                await asyncio.sleep(0.5)
                if await verify_fill(element):
                    return True
                # Fill registered but value was rejected by framework — try JS approach
                logger.debug("Playwright fill was overwritten by framework, trying JS setter")
            except Exception as e:
                logger.debug(f"Playwright fill/type failed, trying JS approach: {e}")
                # Fall through to JS native setter
        else:
            # ---- NON-VISIBLE ELEMENT: try clicking associated label first ----
            try:
                parent_label = await element.evaluate_handle("el => el.closest('label')")
                label_elem = parent_label.as_element()
                if label_elem:
                    await label_elem.scroll_into_view_if_needed()
                    await label_elem.click()
                    return True
            except Exception:
                pass
            try:
                elem_id = await element.get_attribute("id")
                if elem_id:
                    label_elem = await page.query_selector(f'label[for="{elem_id}"]')
                    if label_elem:
                        await label_elem.scroll_into_view_if_needed()
                        await label_elem.click()
                        return True
            except Exception:
                pass

        # ---- JS FALLBACK: native setter + React-compatible events ----
        try:
            await element.evaluate(
                """(el, val) => {
                    const tag = el.tagName.toLowerCase();
                    const isInput = tag === 'input' || tag === 'textarea';
                    
                    if (isInput) {
                        el.focus();
                        const nativeSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        nativeSetter.call(el, '');
                        nativeSetter.call(el, val);
                        el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        try {
                            el.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
                            el.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', bubbles: true }));
                        } catch(e) {}
                        el.blur();
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    } else if (el.isContentEditable) {
                        el.innerText = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    } else {
                        el.value = val;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""",
                answer
            )
            await asyncio.sleep(0.5)
            if await verify_fill(element):
                return True
            # Absolute last resort: try React-specific _valueTracker
            try:
                await element.evaluate(
                    """(el, val) => {
                        el.focus();
                        const nativeSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        nativeSetter.call(el, '');
                        nativeSetter.call(el, val);
                        // React 16+ _valueTracker hack
                        if (el._valueTracker) {
                            el._valueTracker.setValue(val);
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.blur();
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    }""",
                    answer
                )
                await asyncio.sleep(0.3)
                return await verify_fill(element)
            except Exception:
                return False
        except Exception as e:
            logger.debug(f"JS fill failed for element: {e}")
            try:
                await element.evaluate("(el, val) => { el.value = val; el.dispatchEvent(new Event('change', {bubbles: true})); }", answer)
                return True
            except Exception:
                return False

    async def _find_input_by_label_text(self, page, question_text: str) -> object | None:
        """Find an input element by matching its associated label text."""
        q_lower = question_text.lower().strip()
        try:
            labels = await page.query_selector_all("label")
            for label in labels:
                try:
                    label_text = (await label.text_content() or "").strip()
                    if not label_text:
                        continue
                    label_lower = label_text.lower()
                    # Check if label contains question text or vice versa
                    if q_lower == label_lower or (len(q_lower) > 5 and q_lower in label_lower) or (len(label_lower) > 5 and label_lower in q_lower):
                        label_for = await label.get_attribute("for")
                        if label_for:
                            input_elem = await page.query_selector(f"#{CSS.escape(label_for)}")
                            if input_elem:
                                return input_elem
                        # Check inside label
                        input_elem = await label.query_selector("input, select, textarea")
                        if input_elem:
                            return input_elem
                except Exception:
                    pass
        except Exception:
            pass
        return None

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
                            await text_input.type(a, delay=30)
                            await text_input.evaluate("""el => {
                                el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                try {
                                    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
                                    el.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', bubbles: true }));
                                } catch(e) {}
                                el.dispatchEvent(new Event('blur', { bubbles: true }));
                            }""")
                            await asyncio.sleep(0.3)

                            # Trigger Save button so the answer registers and advances
                            save_clicked = await self.click_chatbot_save_button()
                            if not save_clicked:
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

                q_lower = q.lower()
                label_lower = label_text.lower()
                if q_lower == label_lower or (len(q_lower) > 5 and q_lower in label_lower and len(label_lower) <= len(q_lower) + 15) or (len(label_lower) > 5 and label_lower in q_lower and len(q_lower) <= len(label_lower) + 15):
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

    async def _trigger_form_validation(self) -> None:
        """Trigger client-side form validation by blurring all filled fields.
        
        Many SPAs (React/Angular) validate fields on blur. This ensures
        validation state is updated before we attempt to submit.
        """
        page = self._engine.page
        try:
            await page.evaluate("""
                () => {
                    const inputs = document.querySelectorAll(
                        'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="file"]), ' +
                        'select, textarea'
                    );
                    inputs.forEach(el => {
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                        // Also trigger any reportValidity on the form
                        const form = el.closest('form');
                        if (form && typeof form.reportValidity === 'function') {
                            form.reportValidity();
                        }
                    });
                }
            """)
        except Exception:
            pass
    async def click_chatbot_save_button(self) -> bool:
        """Click the Save button specifically within a chatbot/screening panel.

        Naukri's chatbot screening flow shows a prominent 'Save' button at the
        bottom of the chatbot panel after all questions are answered. This method
        scopes the search to the chatbot/modal/dialog container to avoid clicking
        the wrong element on the page.

        Uses a multi-strategy approach with retry:
        1. JS container-scoped scan (chatbot → modal → dialog → body)
        2. Playwright locator scoped to chatbot containers
        3. Fallback: page-wide Playwright locator for Save button
        4. JS fallback page-wide scan

        Returns True if a Save button was found and clicked.
        """
        page = self._engine.page

        for retry in range(3):
            # ── Strategy 1: JS container-scoped scan ──
            # Finds the chatbot/modal container and clicks the best Save button inside it.
            js = r"""() => {
                const savePatterns = ['save', 'save & next', 'save and next', 'save and continue', 'save & continue', 'save details', 'save answer', 'save answers', 'submit', 'next', 'continue', 'apply', 'apply now', 'submit application', 'send'];

                // Ordered container selectors: most specific first
                const containerSelectors = [
                    '[class*="chatbot" i]',
                    '[class*="bot-body" i]',
                    '[class*="chat-body" i]',
                    '[class*="chatbot-container" i]',
                    '[class*="nI-chatbot" i]',
                    '[class*="apply-modal" i]',
                    '[class*="apply-form" i]',
                    '[class*="apply-dialog" i]',
                    '[class*="screening_bot" i]',
                    '[class*="screening-bot" i]',
                    '[class*="screening" i]',
                    '[class*="chat-panel" i]',
                    '[class*="chatbot_" i]',
                    '[class*="modal" i]',
                    '[class*="dialog" i]',
                    '[class*="drawer" i]',
                    '[class*="popup" i]',
                    '[class*="slider" i]',
                    '[class*="overlay" i]',
                ];

                // Find the best container that has a visible Save-like button
                let container = null;
                for (const sel of containerSelectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        // Check if this container has a Save-like button (scan div, span too)
                        const btns = el.querySelectorAll(
                            'button, a, [role="button"], input[type="submit"], input[type="button"], ' +
                            '[class*="btn" i], [class*="button" i], span, div'
                        );
                        for (const btn of btns) {
                            const btnText = (btn.textContent || btn.innerText || btn.value || '').trim().toLowerCase();
                            if (savePatterns.some(p => btnText === p || btnText.startsWith(p + ' '))) {
                                container = el;
                                break;
                            }
                        }
                        if (container) break;
                    }
                    if (container) break;
                }

                // Search within found container, or fall back to full document
                const searchRoot = container || document;
                const candidates = Array.from(searchRoot.querySelectorAll(
                    'button, a, [role="button"], input[type="submit"], input[type="button"], ' +
                    '[class*="btn" i], [class*="button" i], span, div'
                ));

                const results = [];
                for (const el of candidates) {
                    const text = (el.textContent || el.innerText || el.value || '').trim().toLowerCase();
                    if (!text) continue;
                    if (!savePatterns.some(p => text === p || text.startsWith(p + ' ') || text.startsWith(p + '&'))) continue;

                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 15 || rect.height < 15) continue;

                    let score = 0;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
                        score -= 10;
                    }
                    const tag = el.tagName.toUpperCase();

                    // Prefer proper interactive elements
                    if (tag === 'BUTTON') score += 30;
                    else if (tag === 'A' || tag === 'INPUT') score += 20;
                    else score += 5;

                    // Prefer leaf elements (fewer descendants) to get the exact clickable label/button
                    const descendantCount = el.querySelectorAll('*').length;
                    score -= descendantCount * 2;

                    // Exact text match gets highest priority
                    if (text === 'save') score += 50;
                    else if (text.startsWith('save')) score += 40;

                    // Boost if it looks like a primary/CTA button (background color, classes)
                    const bg = style.backgroundColor;
                    if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' && bg !== 'rgb(255, 255, 255)') {
                        score += 20;
                    }
                    const cls = (el.className || '').toString().toLowerCase();
                    if (cls.includes('primary') || cls.includes('cta') || cls.includes('action') || cls.includes('submit')) {
                        score += 15;
                    }

                    // Boost if inside a chatbot/modal container
                    if (el.closest('[class*="chatbot" i], [class*="bot" i], [class*="chat" i], [class*="modal" i], [class*="dialog" i], [class*="drawer" i], [class*="slider" i], [class*="overlay" i]')) {
                        score += 100;
                    }

                    results.push({ el, score, text });
                }

                if (results.length === 0) return null;
                results.sort((a, b) => b.score - a.score);
                const best = results[0].el;
                best.scrollIntoView({ behavior: 'instant', block: 'center' });
                if (best.disabled) best.disabled = false;
                best.removeAttribute('disabled');
                best.removeAttribute('aria-disabled');
                
                // Assign temporary target attribute for Playwright native click
                best.setAttribute('data-agent-click-target', 'true');
                return results[0].text;
            }"""
            try:
                clicked_text = await page.evaluate(js)
                if clicked_text:
                    # Click using Playwright's trusted pointer events click
                    target = page.locator('[data-agent-click-target="true"]').first
                    clicked_via_playwright = False
                    if await target.count() > 0:
                        try:
                            await target.scroll_into_view_if_needed()
                            await asyncio.sleep(0.1)
                            await target.click(timeout=3000)
                            clicked_via_playwright = True
                            logger.info(f"Clicked chatbot Save button via Playwright (attempt {retry + 1}): '{clicked_text}'")
                        except Exception as pe:
                            logger.debug(f"Playwright native click failed, using JS click fallback: {pe}")
                    
                    if not clicked_via_playwright:
                        await page.evaluate(
                            r"""() => {
                                const el = document.querySelector('[data-agent-click-target="true"]');
                                if (el) {
                                    el.click();
                                    el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
                                    el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
                                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                }
                            }"""
                        )
                        logger.info(f"Clicked chatbot Save button via JS fallback (attempt {retry + 1}): '{clicked_text}'")
                    
                    # Clean up the target attribute
                    try:
                        await page.evaluate("() => { const el = document.querySelector('[data-agent-click-target=\"true\"]'); if (el) el.removeAttribute('data-agent-click-target'); }")
                    except Exception:
                        pass
                    
                    await asyncio.sleep(1)
                    return True
            except Exception as e:
                logger.debug(f"Chatbot Save JS scan attempt {retry + 1} failed: {e}")

            # ── Strategy 2: Playwright locator scoped to chatbot containers ──
            container_selectors = [
                '[class*="chatbot"]',
                '[class*="bot-body"]',
                '[class*="apply-modal"]',
                '[class*="modal" i]',
                '[class*="dialog" i]',
            ]
            for container_sel in container_selectors:
                try:
                    container = page.locator(container_sel).first
                    if await container.count() > 0 and await container.is_visible():
                        for btn_text in ("Save", "Save & Next", "Save and Next", "Save and Continue", "Save & Continue", "Save Details", "Save Answer", "Submit", "Next"):
                            btn = container.locator(
                                'button, a, [role="button"], div, span'
                            ).filter(has_text=btn_text).first
                            if (
                                await btn.count() > 0
                                and await btn.is_visible()
                                and await btn.is_enabled()
                            ):
                                await btn.scroll_into_view_if_needed()
                                await asyncio.sleep(0.3)
                                await btn.click()
                                logger.info(
                                    f"Clicked chatbot Save button via Playwright in '{container_sel}': '{btn_text}'"
                                )
                                await asyncio.sleep(1)
                                return True
                except Exception:
                    pass

            # ── Strategy 3: Fallback — page-wide Playwright locator ──
            for btn_text in ("Save", "Save & Next", "Save and Next", "Save & Continue", "Save Details", "Save Answer"):
                try:
                    btn = page.locator('button, [role="button"], div, span').filter(has_text=btn_text).first
                    if (
                        await btn.count() > 0
                        and await btn.is_visible()
                        and await btn.is_enabled()
                    ):
                        await btn.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                        await btn.click()
                        logger.info(f"Clicked Save button via page-wide Playwright fallback: '{btn_text}'")
                        await asyncio.sleep(1)
                        return True
                except Exception:
                    pass

            # ── Strategy 4: JS fallback — any visible button on the page with "Save" text ──
            # This catches buttons in non-standard containers that earlier strategies missed.
            try:
                any_save_clicked = await page.evaluate(
                    r"""() => {
                        const saveTexts = ['save', 'submit', 'next', 'continue', 'apply', 'apply now', 'send'];
                        const candidates = Array.from(document.querySelectorAll(
                            'button, [role="button"], a, input[type="submit"], input[type="button"], ' +
                            '[class*="btn" i], [class*="button" i], [class*="save" i], span, div'
                        ));
                        const results = [];
                        for (const el of candidates) {
                            const text = (el.textContent || el.innerText || el.value || '').trim().toLowerCase();
                            if (!text || !saveTexts.some(st => text === st || text.startsWith(st + ' ') || text.startsWith(st + '&'))) continue;
                            const style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
                            const rect = el.getBoundingClientRect();
                            if (rect.width < 20 || rect.height < 20) continue;
                            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                            
                            let score = 0;
                            if (el.tagName === 'BUTTON') score += 20;
                            if (text === 'save') score += 30;
                            else if (text.startsWith('save')) score += 20;
                            
                            // Prefer leaf elements (fewer descendants)
                            const descendantCount = el.querySelectorAll('*').length;
                            score -= descendantCount * 2;
                            
                            // Boost for primary/CTA styling (colored background)
                            const bg = style.backgroundColor;
                            if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' && bg !== 'rgb(255, 255, 255)') score += 15;
                            if (el.className.toLowerCase().includes('primary') || el.className.toLowerCase().includes('cta')) score += 10;
                            
                            // Boost if inside a chatbot/modal/drawer container
                            if (el.closest('[class*="chatbot" i], [class*="bot" i], [class*="chat" i], [class*="modal" i], [class*="dialog" i], [class*="drawer" i], [class*="slider" i], [class*="overlay" i]')) {
                                score += 100;
                            }
                            
                            results.push({ el, score, text });
                        }
                        if (results.length === 0) return null;
                        results.sort((a, b) => b.score - a.score);
                        const best = results[0].el;
                        best.scrollIntoView({ behavior: 'instant', block: 'center' });
                        if (best.disabled) best.disabled = false;
                        best.removeAttribute('disabled');
                        best.removeAttribute('aria-disabled');
                        
                        best.setAttribute('data-agent-click-target', 'true');
                        return results[0].text;
                    }"""
                )
                if any_save_clicked:
                    # Click using Playwright
                    target = page.locator('[data-agent-click-target="true"]').first
                    clicked_via_playwright = False
                    if await target.count() > 0:
                        try:
                            await target.scroll_into_view_if_needed()
                            await asyncio.sleep(0.1)
                            await target.click(timeout=3000)
                            clicked_via_playwright = True
                            logger.info(f"Clicked Save button via page-wide Playwright: '{any_save_clicked}'")
                        except Exception as pe:
                            logger.debug(f"Page-wide Playwright native click failed: {pe}")
                            
                    if not clicked_via_playwright:
                        await page.evaluate(
                            r"""() => {
                                const el = document.querySelector('[data-agent-click-target="true"]');
                                if (el) {
                                    el.click();
                                    el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
                                    el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
                                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                }
                            }"""
                        )
                        logger.info(f"Clicked Save button via page-wide JS fallback: '{any_save_clicked}'")
                        
                    # Clean up the target attribute
                    try:
                        await page.evaluate("() => { const el = document.querySelector('[data-agent-click-target=\"true\"]'); if (el) el.removeAttribute('data-agent-click-target'); }")
                    except Exception:
                        pass
                        
                    await asyncio.sleep(1)
                    return True
            except Exception as e:
                logger.debug(f"Page-wide JS Save fallback failed: {e}")

            await asyncio.sleep(0.8)

        logger.debug("Chatbot Save button not found after 3 attempts")
        return False

    async def click_intermediate_save_button(self) -> bool:
        """Click an intermediate Save/Next/Continue button (NOT Submit/Apply).

        In Naukri's screening flow, after filling a question there is often a
        'Save' button that must be clicked before the answer registers.

        For chatbot flows, delegates to click_chatbot_save_button() first.
        For standard forms, tries Playwright locators then JS broad scan with retry.
        Returns True if a Save/Next/Continue button was found and clicked.
        """
        # For chatbot flows, use the dedicated chatbot-scoped method first
        if await self.is_chatbot_flow():
            result = await self.click_chatbot_save_button()
            if result:
                return True
            # Fall through to generic strategies if chatbot-specific method fails

        page = self._engine.page

        for retry in range(3):
            # ── Strategy 1: Playwright native locators ──
            for text in ("Save", "Save & Next", "Save and Continue", "Next", "Continue"):
                try:
                    btn = page.locator(
                        'button, input[type="submit"], input[type="button"], '
                        '[role="button"]'
                    ).filter(has_text=text).first
                    if (
                        await btn.count() > 0
                        and await btn.first.is_visible()
                        and await btn.first.is_enabled()
                    ):
                        await btn.first.scroll_into_view_if_needed()
                        await asyncio.sleep(0.2)
                        await btn.first.click()
                        logger.debug(f"Clicked Save button via Playwright: '{text}'")
                        return True
                except Exception:
                    pass

            # ── Strategy 2: JS broad scan (catches non-standard
            #    elements like <div>, <span>, <a> with matching text) ──
            js = """() => {
                const saveTexts = ['save', 'next', 'continue'];
                const candidates = Array.from(
                    document.querySelectorAll(
                        'button, input[type=\"button\"], input[type=\"submit\"], ' +
                        'a, [role=\"button\"], [onclick], ' +
                        '[class*=\"btn\" i], [class*=\"button\" i], ' +
                        '[class*=\"save\" i], [class*=\"submit\" i], ' +
                        'span, div, label'
                    )
                );
                const results = [];
                for (const el of candidates) {
                    const text = (el.textContent || el.innerText || el.value || '').trim().toLowerCase();
                    if (!text) continue;
                    const match = saveTexts.some(st =>
                        text === st || text.startsWith(st + ' ') || text.startsWith(st + '&')
                    );
                    if (!match) continue;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 20 || rect.height < 20) continue;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                    let depth = (el.tagName === 'BUTTON' || el.tagName === 'INPUT' || el.tagName === 'A') ? 0 : 1;
                    
                    // Prefer leaf elements (fewer descendants)
                    const descendantCount = el.querySelectorAll('*').length;
                    depth += descendantCount * 0.1;
                    
                    // Prefer buttons inside modal/chatbot/drawer/slider containers
                    if (el.closest('[class*="modal" i], [class*="chatbot" i], [class*="dialog" i], [class*="apply" i], [class*="drawer" i], [class*="slider" i], [class*="overlay" i]')) {
                        depth -= 5;
                    }
                    results.push({ el, depth, text });
                }
                if (results.length === 0) return null;
                results.sort((a, b) => a.depth - b.depth);
                const best = results[0].el;
                best.scrollIntoView({ behavior: 'instant', block: 'center' });
                if (best.disabled) best.disabled = false;
                best.removeAttribute('disabled');
                best.removeAttribute('aria-disabled');
                
                best.setAttribute('data-agent-click-target', 'true');
                return results[0].text;
            }"""
            try:
                clicked_text = await page.evaluate(js)
                if clicked_text:
                    # Click using Playwright's trusted pointer events click
                    target = page.locator('[data-agent-click-target="true"]').first
                    clicked_via_playwright = False
                    if await target.count() > 0:
                        try:
                            await target.scroll_into_view_if_needed()
                            await asyncio.sleep(0.1)
                            await target.click(timeout=3000)
                            clicked_via_playwright = True
                            logger.debug(f"Clicked Save button via Playwright: '{clicked_text}'")
                        except Exception as pe:
                            logger.debug(f"Playwright native click failed on intermediate Save: {pe}")
                            
                    if not clicked_via_playwright:
                        await page.evaluate(
                            r"""() => {
                                const el = document.querySelector('[data-agent-click-target="true"]');
                                if (el) {
                                    el.click();
                                    el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
                                    el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
                                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                }
                            }"""
                        )
                        logger.debug(f"Clicked Save button via JS fallback: '{clicked_text}'")
                        
                    # Clean up the target attribute
                    try:
                        await page.evaluate("() => { const el = document.querySelector('[data-agent-click-target=\"true\"]'); if (el) el.removeAttribute('data-agent-click-target'); }")
                    except Exception:
                        pass
                        
                    return True
            except Exception as e:
                logger.debug(f"JS intermediate save click failed: {e}")

            await asyncio.sleep(0.8)

        return False

    async def submit_application(self) -> bool:
        """Click the submit/apply button to finalize the application.

        For chatbot flows, prioritizes the 'Save' button since that IS the
        final submit action in Naukri's chatbot screening.

        Returns:
            True if a button was successfully clicked, False otherwise.
        """
        page = self._engine.page
        is_chatbot = await self.is_chatbot_flow()

        # For chatbot flows, try the dedicated chatbot Save button first
        if is_chatbot:
            save_clicked = await self.click_chatbot_save_button()
            if save_clicked:
                logger.info("submit_application: Used chatbot Save button for submission")
                return True

        # Try a robust JavaScript evaluator click to find the best visible, enabled button
        # In chatbot flows, "Save" gets the highest score since it's the submit action
        js_click_script = """
        (isChatbot) => {
            const getScore = (el) => {
                const text = el.textContent.trim().toLowerCase() || el.value?.trim().toLowerCase() || "";
                let score = 0;

                if (isChatbot) {
                    // In chatbot flows, Save IS the submit action — highest priority
                    if (text === 'save' || text.startsWith('save ') || text.startsWith('save&')) score = 150;
                    else if (text.includes('submit') || text === 'apply' || text === 'apply now') score = 100;
                    else if (text.includes('next') || text.includes('continue') || text.includes('send')) score = 80;
                    else if (text.includes('confirm') || text.includes('proceed')) score = 70;
                } else {
                    if (text.includes('submit') || text === 'apply' || text === 'apply now') score = 100;
                    else if (text.includes('save') || text.includes('next') || text.includes('continue') || text.includes('send')) score = 80;
                    else if (text.includes('confirm') || text.includes('proceed')) score = 70;
                }
                
                if (score > 0) {
                    // Boost score if inside a modal, popup, or chatbot container
                    if (el.closest('[class*="modal" i], [class*="dialog" i], [class*="popup" i], [class*="chatbot"], [class*="chat" i], [class*="bot" i], [class*="drawer" i], [class*="slider" i], [class*="overlay" i]')) {
                        score += 50;
                    }
                    // Boost if it's a primary-styled button (has background color)
                    const style = window.getComputedStyle(el);
                    const bg = style.backgroundColor;
                    if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' && bg !== 'rgb(255, 255, 255)') {
                        score += 10;
                    }
                    // Prefer leaf elements
                    const descendantCount = el.querySelectorAll('*').length;
                    score -= descendantCount * 2;
                }
                return score;
            };

            const candidates = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn, a.button, [class*="btn" i], [class*="button" i], span, div'));
            
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
                best.scrollIntoView({ behavior: 'instant', block: 'center' });
                best.setAttribute('data-agent-click-target', 'true');
                return true;
            }
            return false;
        }
        """
        try:
            clicked = await page.evaluate(js_click_script, is_chatbot)
            if clicked:
                target = page.locator('[data-agent-click-target="true"]').first
                clicked_via_playwright = False
                if await target.count() > 0:
                    try:
                        await target.scroll_into_view_if_needed()
                        await asyncio.sleep(0.1)
                        await target.click(timeout=3000)
                        clicked_via_playwright = True
                        logger.debug("Successfully clicked submit/apply button via Playwright.")
                    except Exception as pe:
                        logger.debug(f"Playwright native submit click failed, falling back: {pe}")
                        
                if not clicked_via_playwright:
                    await page.evaluate(
                        r"""() => {
                            const el = document.querySelector('[data-agent-click-target="true"]');
                            if (el) {
                                el.click();
                                el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
                                el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
                                el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                            }
                        }"""
                    )
                    logger.debug("Successfully clicked submit/apply button via JS fallback.")
                    
                # Clean up target attribute
                try:
                    await page.evaluate("() => { const el = document.querySelector('[data-agent-click-target=\"true\"]'); if (el) el.removeAttribute('data-agent-click-target'); }")
                except Exception:
                    pass
                    
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
            body_text = await page.evaluate("document.body.innerText")
            failure_phrases = [
                "application was not accepted",
                "please answer all mandatory questions",
                "please answer the mandatory questions",
                "incomplete information",
                "reapplying",
            ]
            for phrase in failure_phrases:
                if phrase in body_text.lower():
                    return "Incomplete information / unanswered mandatory questions"
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
                "application received",
                "successfully applied",
                "thank you for applying",
                "application sent",
                "your application has been sent",
                "we have received your application",
                "your application is submitted",
                "application has been submitted",
                "you have successfully applied",
                "successfully submitted",
                "applied on",
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
