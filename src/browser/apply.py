"""
Naukri.com job application submission handler.

Handles the complete apply flow:
1. Click the Apply button on job detail pages
2. Detect the type of application (direct, with questions, external)
3. Fill screening questionnaire fields using AI
4. Confirm submission and verify success
"""

from __future__ import annotations

import asyncio

from src.core.interfaces import IBrowserEngine, IBrowserInteractions, IQuestionAnswerer
from src.config.constants import (
    ELEMENT_TIMEOUT,
    JobDetailSelectors,
    ApplyFlowSelectors,
    ApplicationStatus,
)
from src.config.settings import Settings
from src.utils.logger import get_logger, log_info, log_success, log_error, log_warning
import contextlib

logger = get_logger(__name__)


class JobApplier:
    """
    Handles the job application submission flow on Naukri.com.

    Supports:
    - Direct one-click apply
    - Apply with screening questions (auto-filled by AI)
    - Detection and skipping of external apply redirects
    - Chatbot/overlay handling

    Usage:
        applier = JobApplier(engine, settings, question_answerer)
        result = await applier.apply_to_job(job_data)
    """

    def __init__(
        self,
        engine: IBrowserEngine,
        interactions: IBrowserInteractions,
        settings: Settings,
        question_answerer: IQuestionAnswerer,
    ) -> None:
        self._engine = engine
        self._interactions = interactions
        self._settings = settings
        self._qa = question_answerer

    async def apply_to_job(self, job_data: dict) -> dict:
        """
        Attempt to apply to a job on the current page.

        The browser should already be on the job detail page.

        Args:
            job_data: Dict with job title, company, url, etc.

        Returns:
            Dict with keys:
                - status: ApplicationStatus constant
                - error_message: Error details if failed
        """
        try:
            # Step 1: Close any blocking popups/chatbots
            await self._interactions.close_popups()
            await asyncio.sleep(1)

            # Step 2: Check if already applied
            already_applied = await self._interactions.element_exists(
                JobDetailSelectors.ALREADY_APPLIED
            )
            if already_applied:
                log_warning(f"Already applied: {job_data.get('title', '')}")
                return {
                    "status": ApplicationStatus.SKIPPED_ALREADY_APPLIED,
                    "error_message": "",
                }

            # Step 3: Check for external apply
            is_external = await self._interactions.element_exists(JobDetailSelectors.EXTERNAL_APPLY)
            if is_external and self._settings.application.skip_external_apply:
                log_warning(f"External apply (skipped): {job_data.get('title', '')}")
                return {
                    "status": ApplicationStatus.SKIPPED_EXTERNAL,
                    "error_message": "External application — skipped per config",
                }

            # Step 4: Find and click the Apply button
            log_info(f"Applying to: {job_data.get('title', '')} @ {job_data.get('company', '')}")

            apply_clicked = await self._click_apply_button()
            if not apply_clicked:
                log_error("Could not find or click Apply button")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": "Apply button not found or not clickable",
                }

            await asyncio.sleep(2)

            # Step 5: Handle the apply flow (questions, confirmation, etc.)
            result = await self._handle_apply_flow(job_data)
            return result

        except Exception as e:
            log_error(f"Application failed: {e}")
            logger.exception("Application error details")
            return {
                "status": ApplicationStatus.ERROR,
                "error_message": str(e),
            }

    async def _click_apply_button(self) -> bool:
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

    async def _handle_apply_flow(self, job_data: dict) -> dict:
        """
        Handle the post-click apply flow, which may include:
        - Direct success (one-click apply)
        - Screening questions form
        - Chatbot-style Q&A
        - Resume upload prompt
        """
        # Wait a moment for the apply modal/flow to appear
        await asyncio.sleep(2)

        # Check for immediate success
        if await self._check_application_success():
            log_success(f"Applied successfully (direct): {job_data.get('title', '')}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Check for screening questions
        has_questions = await self._detect_screening_questions()
        if has_questions:
            log_info("Screening questions detected — filling with AI...")
            answered = await self._fill_screening_questions(job_data)
            if not answered:
                log_warning("Could not fill all screening questions")

            # Submit after filling
            await self._submit_application()
            await asyncio.sleep(2)

            if await self._check_application_success():
                log_success(f"Applied successfully (with questions): {job_data.get('title', '')}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Try submitting any visible form
        await self._submit_application()
        await asyncio.sleep(3)

        # Final success check
        if await self._check_application_success():
            log_success(f"Applied successfully: {job_data.get('title', '')}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Check if already applied (post-click state)
        if await self._interactions.element_exists(JobDetailSelectors.ALREADY_APPLIED):
            log_success(
                f"Application confirmed (already applied indicator): {job_data.get('title', '')}"
            )
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # If we get here, we're not sure if the application went through
        log_warning(f"Application status uncertain: {job_data.get('title', '')}")
        return {
            "status": ApplicationStatus.APPLIED,
            "error_message": "Status uncertain — could not confirm success indicator",
        }

    async def _detect_screening_questions(self) -> bool:
        """Check if the apply flow is showing screening questions."""
        page = self._engine.page

        # Check for question containers
        question_indicators = [
            ApplyFlowSelectors.QUESTION_CONTAINER,
            ApplyFlowSelectors.APPLY_FORM,
            'form[class*="apply"]',
            '[class*="chatbot-msg"]',
            '[class*="screening"]',
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

    async def _fill_screening_questions(self, job_data: dict) -> bool:
        """
        Extract screening questions from the page and fill them using AI.

        Returns:
            True if questions were successfully filled.
        """
        try:
            # Collect questions from the page
            questions = await self._extract_questions()
            if not questions:
                logger.debug("No questions extracted from the page")
                return True  # No questions to fill

            # Get AI answers
            answers = await self._qa.answer_questions(questions, job_data)

            # Fill in the answers
            for answer_data in answers:
                question_text = answer_data.get("question", "")
                answer = answer_data.get("answer", "")
                confidence = answer_data.get("confidence", "low")

                if not answer or confidence == "low":
                    logger.warning(f"Skipping low-confidence answer for: {question_text}")
                    continue

                await self._fill_answer(question_text, answer)
                await self._interactions.action_delay()

            return True

        except Exception as e:
            logger.error(f"Failed to fill screening questions: {e}")
            return False

    async def _extract_questions(self) -> list[dict]:
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

    async def _fill_answer(self, question_text: str, answer: str) -> None:
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

    async def _submit_application(self) -> None:
        """Click the submit/apply button to finalize the application."""
        submit_selectors = [
            ApplyFlowSelectors.SUBMIT_BUTTON,
            ApplyFlowSelectors.NEXT_BUTTON,
            '//button[contains(text(), "Submit")]',
            '//button[contains(text(), "Apply")]',
            'button[type="submit"]',
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

    async def _check_application_success(self) -> bool:
        """Check if the application was submitted successfully."""
        page = self._engine.page

        # Check for success indicators
        success_selectors = [
            ApplyFlowSelectors.APPLICATION_SUCCESS,
            '//*[contains(text(), "successfully")]',
            '//*[contains(text(), "submitted")]',
            '//*[contains(text(), "received your application")]',
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
