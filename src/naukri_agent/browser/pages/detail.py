"""
JobDetailPage Page Object for Naukri.com.
Encapsulates parsing job details, detecting screening forms, answering questions, and submitting applications.
"""

from __future__ import annotations

import asyncio
import contextlib

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
        return await self._interactions.element_exists(JobDetailSelectors.ALREADY_APPLIED)

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

        return {
            "description": description,
            "skills": ", ".join(skills),
            "experience_detail": clean_text(experience),
            "salary_detail": clean_text(salary),
            "location_detail": clean_text(location),
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

        # Strategy 2: Try common CSS patterns
        css_patterns = [
            'button[class*="apply"]',
            'button[id*="apply"]',
            'a[class*="apply"]',
            '[class*="apply-button"]',
        ]
        for pattern in css_patterns:
            clicked = await self._interactions.safe_click(pattern, timeout=3000)
            if clicked:
                return True

        # Strategy 3: JavaScript click (bypasses overlays)
        page = self._engine.page
        try:
            result = await page.evaluate(
                """
                () => {
                    const buttons = [...document.querySelectorAll('button, a')];
                    const applyBtn = buttons.find(btn => {
                        const text = btn.textContent.trim().toLowerCase();
                        return text.includes('apply') && !text.includes('applied');
                    });
                    if (applyBtn) {
                        applyBtn.click();
                        return true;
                    }
                    return false;
                }
            """
            )
            if result:
                return True
        except Exception as e:
            logger.debug(f"JS apply click failed: {e}")

        return False

    async def detect_screening_questions(self) -> bool:
        """Check if the apply flow is showing screening questions."""
        page = self._engine.page

        # Check for question containers
        question_indicators = [
            ApplyFlowSelectors.QUESTION_CONTAINER,
            ApplyFlowSelectors.APPLY_FORM,
            ApplyFlowSelectors.FORM_FALLBACK,
            ApplyFlowSelectors.CHATBOT_MSG_FALLBACK,
            ApplyFlowSelectors.SCREENING_FALLBACK,
        ]

        for selector in question_indicators:
            if await self._interactions.element_exists(selector):
                return True

        # Check for text inputs or dropdowns in modal/form context
        inputs = await page.query_selector_all(
            f"{ApplyFlowSelectors.APPLY_FORM} input, "
            f"{ApplyFlowSelectors.APPLY_FORM} select, "
            f"{ApplyFlowSelectors.APPLY_FORM} textarea"
        )
        return bool(inputs)

    async def extract_screening_questions(self) -> list[dict]:
        """
        Extract screening questions from the current apply form.

        Returns:
            List of dicts with question text, type, and available options.
        """
        page = self._engine.page
        questions: list[dict] = []

        try:
            # Look for labeled form fields
            labels = await page.query_selector_all("label")
            for i, label in enumerate(labels):
                label_text = (await label.text_content() or "").strip()
                if not label_text or len(label_text) < 3:
                    continue

                # Determine input type
                label_for = await label.get_attribute("for")
                input_type = "text"
                options: list[str] = []

                if label_for:
                    input_elem = await page.query_selector(f"#{label_for}")
                    if input_elem:
                        tag = await input_elem.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "select":
                            input_type = "dropdown"
                            option_elems = await input_elem.query_selector_all("option")
                            for opt in option_elems:
                                opt_text = (await opt.text_content() or "").strip()
                                if opt_text and opt_text.lower() not in (
                                    "select",
                                    "--select--",
                                    "choose",
                                ):
                                    options.append(opt_text)

                questions.append(
                    {
                        "question": label_text,
                        "type": input_type,
                        "options": options,
                        "index": i,
                    }
                )

            # Also look for chatbot-style questions
            chatbot_msgs = await page.query_selector_all(
                '[class*="chatbot-msg"], [class*="bot-msg"]'
            )
            for _i, msg in enumerate(chatbot_msgs):
                msg_text = (await msg.text_content() or "").strip()
                if msg_text and "?" in msg_text:
                    questions.append(
                        {
                            "question": msg_text,
                            "type": "text",
                            "options": [],
                            "index": len(questions),
                        }
                    )

        except Exception as e:
            logger.debug(f"Question extraction error: {e}")

        logger.info(f"Extracted {len(questions)} screening questions")
        return questions

    async def fill_answer(self, question_text: str, answer: str) -> None:
        """
        Fill a single answer into the appropriate form field on the page.

        Uses proximity-based matching to find the input closest to the
        question label text.
        """
        page = self._engine.page

        try:
            # Find labels matching the question
            labels = await page.query_selector_all("label")
            for label in labels:
                label_text = (await label.text_content() or "").strip()
                if question_text.lower()[:30] in label_text.lower():
                    # Found the matching label — find associated input
                    label_for = await label.get_attribute("for")

                    if label_for:
                        input_elem = await page.query_selector(f"#{label_for}")
                    else:
                        # Try sibling or child input
                        input_elem = await label.query_selector("input, select, textarea")
                        if not input_elem:
                            parent = await label.evaluate_handle("el => el.parentElement")
                            input_elem = await parent.as_element().query_selector(
                                "input, select, textarea"
                            )

                    if input_elem:
                        tag = await input_elem.evaluate("el => el.tagName.toLowerCase()")

                        if tag == "select":
                            await self._select_dropdown_option(input_elem, answer)
                        elif tag == "textarea":
                            await input_elem.fill(answer)
                        else:
                            input_type = await input_elem.get_attribute("type") or "text"
                            if input_type == "radio":
                                await self._select_radio_option(label, answer)
                            elif input_type == "checkbox":
                                is_checked = await input_elem.is_checked()
                                should_check = answer.lower() in ("yes", "true", "checked", "1")
                                if should_check != is_checked:
                                    await input_elem.click()
                            else:
                                await input_elem.fill("")
                                await input_elem.type(answer, delay=50)

                        logger.debug(f"Filled '{question_text[:40]}' with '{answer[:40]}'")
                        return

        except Exception as e:
            logger.debug(f"Failed to fill answer for '{question_text[:40]}': {e}")

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

        except Exception as e:
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

        except Exception as e:
            logger.debug(f"Radio selection failed: {e}")

    async def submit_application(self) -> None:
        """Click the submit/apply button to finalize the application."""
        submit_selectors = [
            ApplyFlowSelectors.SUBMIT_BUTTON,
            ApplyFlowSelectors.NEXT_BUTTON,
            ApplyFlowSelectors.GENERIC_SUBMIT,
            ApplyFlowSelectors.GENERIC_APPLY,
            ApplyFlowSelectors.GENERIC_SUBMIT_TYPE,
        ]

        for selector in submit_selectors:
            clicked = await self._interactions.safe_click(selector, timeout=3000)
            if clicked:
                logger.debug(f"Clicked submit with: {selector}")
                return

        # JavaScript fallback
        page = self._engine.page
        with contextlib.suppress(Exception):
            await page.evaluate(
                """
                () => {
                    const buttons = [...document.querySelectorAll('button')];
                    const submitBtn = buttons.find(btn => {
                        const text = btn.textContent.trim().toLowerCase();
                        return text.includes('submit') || text === 'apply';
                    });
                    if (submitBtn) submitBtn.click();
                }
            """
            )

    async def check_application_success(self) -> bool:
        """Check if the application was submitted successfully."""
        page = self._engine.page

        # Check for success indicators
        success_selectors = [
            ApplyFlowSelectors.APPLICATION_SUCCESS,
            '//*[contains(text(), "successfully")]',
            ApplyFlowSelectors.SUCCESS_SUBMITTED,
            ApplyFlowSelectors.SUCCESS_RECEIVED,
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
            ]
            for phrase in success_phrases:
                if phrase in body_text.lower():
                    return True
        except Exception:
            pass

        return False
