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
import re

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job
from src.naukri_agent.bot.interfaces import IQuestionAnswerer
from src.naukri_agent.utils.logger import (
    get_logger,
    log_error,
    log_info,
    log_success,
    log_warning,
)

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
        applier = JobApplier(detail_page, settings, question_answerer)
        result = await applier.apply_to_job(job_data)
    """

    def __init__(
        self,
        detail_page: JobDetailPage,
        settings: Settings,
        question_answerer: IQuestionAnswerer,
    ) -> None:
        self._detail_page = detail_page
        self._settings = settings
        self._qa = question_answerer

    async def apply_to_job(self, job: Job) -> dict:
        """
        Attempt to apply to a job on the current page.

        The browser should already be on the job detail page.

        Args:
            job: Job domain entity.

        Returns:
            Dict with keys:
                - status: ApplicationStatus constant
                - error_message: Error details if failed
        """
        try:
            # Step 1: Close any blocking popups/chatbots
            await self._detail_page.close_popups()
            await asyncio.sleep(1)

            # Step 2: Check if already applied
            already_applied = await self._detail_page.is_already_applied()
            if already_applied:
                log_warning(f"Already applied: {job.title}")
                return {
                    "status": ApplicationStatus.SKIPPED_ALREADY_APPLIED,
                    "error_message": "",
                }

            # Step 3: Check for external apply
            is_external = await self._detail_page.is_external_apply()
            if is_external:
                log_warning(f"External apply detected: {job.title}")
                external_url = None
                if getattr(self._settings.application, "collect_external_jobs", False):
                    external_url = await self._detail_page.get_external_apply_url()
                return {
                    "status": ApplicationStatus.SKIPPED_EXTERNAL,
                    "error_message": "External application — skipped and extracted link",
                    "external_url": external_url,
                }

            # Step 4: Find and click the Apply button
            log_info(f"Applying to: {job.title} @ {job.company}")

            apply_clicked = await self._detail_page.click_apply_button()
            if not apply_clicked:
                log_error("Could not find or click Apply button")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": "Apply button not found or not clickable",
                }

            # Wait for redirect/navigation (if any) or modal rendering
            try:
                await self._detail_page._interactions.wait_for_navigation_complete(timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # Step 5: Handle the apply flow (questions, confirmation, etc.)
            result = await self._handle_apply_flow(job)
            return result

        except (PlaywrightTimeoutError, PlaywrightError) as e:
            log_error(f"Application failed: {e}")
            logger.exception("Application error details")
            return {
                "status": ApplicationStatus.ERROR,
                "error_message": str(e),
            }

    async def _handle_apply_flow(self, job: Job) -> dict:
        """
        Handle the post-click apply flow, which may include:
        - Direct success (one-click apply)
        - Screening questions form
        - Chatbot-style Q&A
        - Resume upload prompt
        """
        # Wait a moment for the apply modal/flow to appear
        await asyncio.sleep(2)

        # Check for early failure indicators
        failure_msg = await self._detail_page.check_application_failure()
        if failure_msg:
            if not getattr(
                self._settings.application, "answer_questions_with_pdf", True
            ) and self._is_unanswered_questions_failure(failure_msg):
                log_warning(
                    f"Screening questions/mandatory fields detected but 'answer_questions_with_pdf' is false. Skipping job: {job.title}"
                )
                return {
                    "status": ApplicationStatus.SKIPPED_SCREENING,
                    "error_message": f"Skipped: {failure_msg} and answer_questions_with_pdf is false",
                }
            log_error(f"Application failed: {failure_msg}")
            return {
                "status": ApplicationStatus.FAILED,
                "error_message": f"Application rejected: {failure_msg}",
            }

        # Check for immediate success
        if await self._detail_page.check_application_success():
            log_success(f"Applied successfully (direct): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Check for screening questions
        has_questions = await self._detail_page.detect_screening_questions()
        if has_questions:
            if not getattr(self._settings.application, "answer_questions_with_pdf", True):
                log_warning(
                    f"Screening questions detected but 'answer_questions_with_pdf' is false. Skipping job: {job.title}"
                )
                return {
                    "status": ApplicationStatus.SKIPPED_SCREENING,
                    "error_message": "Skipped: Screening questions detected and answer_questions_with_pdf is false",
                }

            log_info("Screening questions detected — filling with AI...")
            answered = await self._fill_screening_questions(job)
            if not answered:
                log_warning("Could not fill all screening questions")

            # Submit after filling
            await self._detail_page.submit_application()
            await asyncio.sleep(2)

            # Check for failure indicators
            failure_msg = await self._detail_page.check_application_failure()
            if failure_msg:
                if not getattr(
                    self._settings.application, "answer_questions_with_pdf", True
                ) and self._is_unanswered_questions_failure(failure_msg):
                    log_warning(
                        f"Screening questions/mandatory fields detected but 'answer_questions_with_pdf' is false. Skipping job: {job.title}"
                    )
                    return {
                        "status": ApplicationStatus.SKIPPED_SCREENING,
                        "error_message": f"Skipped: {failure_msg} and answer_questions_with_pdf is false",
                    }
                log_error(f"Application failed: {failure_msg}")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": f"Application rejected: {failure_msg}",
                }

            if await self._detail_page.check_application_success():
                log_success(f"Applied successfully (with questions): {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Try submitting any visible form
        await self._detail_page.submit_application()

        # Final success check with robust polling (up to 10 seconds)
        for _ in range(20):
            await asyncio.sleep(0.5)
            # Check for failure indicators
            failure_msg = await self._detail_page.check_application_failure()
            if failure_msg:
                if not getattr(
                    self._settings.application, "answer_questions_with_pdf", True
                ) and self._is_unanswered_questions_failure(failure_msg):
                    log_warning(
                        f"Screening questions/mandatory fields detected but 'answer_questions_with_pdf' is false. Skipping job: {job.title}"
                    )
                    return {
                        "status": ApplicationStatus.SKIPPED_SCREENING,
                        "error_message": f"Skipped: {failure_msg} and answer_questions_with_pdf is false",
                    }
                log_error(f"Application failed: {failure_msg}")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": f"Application rejected: {failure_msg}",
                }

            if await self._detail_page.check_application_success():
                log_success(f"Applied successfully: {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}

            if await self._detail_page.is_already_applied():
                log_success(f"Application confirmed (already applied indicator): {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # If we get here, we're not sure if the application went through
        log_warning(f"Application status uncertain: {job.title}")
        return {
            "status": ApplicationStatus.UNCERTAIN,
            "error_message": "Status uncertain — could not confirm success indicator",
        }

    def _is_unanswered_questions_failure(self, failure_msg: str) -> bool:
        if not failure_msg:
            return False
        msg_lower = failure_msg.lower()
        return any(
            term in msg_lower
            for term in ("unanswered", "incomplete", "mandatory", "question", "required")
        )

    def _generate_safe_fallback_for_question(self, question: dict) -> str:
        q_text = question.get("question", "").lower()
        q_type = question.get("type")
        options = [o.get("text", "") for o in question.get("options", [])]

        # Helper to pick closest choice
        def pick_option(keywords, default):
            for kw in keywords:
                for opt in options:
                    if kw in opt.lower():
                        return opt
            return options[0] if options else default

        if q_type in ("radio", "dropdown", "checkbox"):
            if "reloc" in q_text or "travel" in q_text or "shift" in q_text or "agree" in q_text:
                return pick_option(["yes", "agree", "true", "y"], "Yes")
            if "notice" in q_text:
                return pick_option(["immediate", "0 days", "15 days", "serving"], "Immediate")
            if "gender" in q_text:
                return pick_option(["male"], "Male")
            if "experience" in q_text or "years" in q_text:
                return pick_option(["1", "1 year", "0-1", "1-2"], options[0] if options else "1")
            if "ctc" in q_text or "salary" in q_text:
                return pick_option(["4", "5", "6"], options[0] if options else "6 LPA")
            if "location" in q_text or "city" in q_text:
                return pick_option(["pune"], "Pune")
            return options[0] if options else "Yes"
        else:
            # Text / number / date fields
            if "experience" in q_text or "years" in q_text or "month" in q_text:
                return "1"
            if "ctc" in q_text or "salary" in q_text:
                if "expected" in q_text:
                    return (
                        "600000"
                        if "rupee" in q_text or "rs" in q_text or "annual" in q_text
                        else "6"
                    )
                return (
                    "440000" if "rupee" in q_text or "rs" in q_text or "annual" in q_text else "4.4"
                )
            if "notice" in q_text:
                return "Immediate"
            if "location" in q_text or "city" in q_text:
                return "Pune"
            if "phone" in q_text or "mobile" in q_text:
                return "9921626877"
            if "email" in q_text:
                return "pushpak262001@gmail.com"
            if "name" in q_text:
                return "Pushpak Pandharpatte"
            if "why" in q_text or "join" in q_text or "fit" in q_text:
                return "I am a skilled Full-Stack Developer with hands-on experience in Java, Spring Boot, and React. I am passionate about building scalable, high-performance web applications and would love to contribute to your team."
            if "project" in q_text or "describe" in q_text:
                return "I built a production-grade autonomous RPA agent using Python, Playwright, and Gemini API, and a real-time ride sharing platform using Spring Boot and React."
            return "Yes"

    async def _fill_screening_questions(self, job: Job) -> bool:
        """
        Extract, answer, and fill screening questions iteratively.
        Handles dynamic follow-up questions and validates mandatory fields.
        """
        try:
            max_attempts = 5
            attempt = 0

            while attempt < max_attempts:
                attempt += 1
                logger.info(f"Screening questions fill attempt {attempt}/{max_attempts}...")

                # Extract questions
                questions = await self._detail_page.extract_screening_questions()
                if not questions:
                    logger.debug("No screening questions found on page.")
                    break

                # Filter for unfilled fields
                unfilled_questions = []
                for q in questions:
                    val = (q.get("value") or "").strip()
                    is_unfilled = not val or val.lower() in ("select", "--select--", "choose")
                    if is_unfilled:
                        unfilled_questions.append(q)

                if not unfilled_questions:
                    logger.info("All screening questions are filled.")
                    break

                logger.info(
                    f"Found {len(unfilled_questions)} unfilled questions. Generating answers..."
                )

                # Answer them
                answers = await self._qa.answer_questions(unfilled_questions, job)

                filled_any = False
                for ans in answers:
                    q_text = ans.get("question", "")
                    q_id = ans.get("id") or ""
                    a_val = str(ans.get("answer", "")).strip()

                    # Find matching question in unfilled
                    matching_q = next(
                        (
                            uq
                            for uq in unfilled_questions
                            if uq.get("question") == q_text or uq.get("id") == q_id
                        ),
                        None,
                    )
                    if not matching_q:
                        continue

                    # If no answer generated, use safe local fallback
                    if not a_val:
                        a_val = self._generate_safe_fallback_for_question(matching_q)
                        logger.info(f"Using safe fallback '{a_val}' for: '{q_text}'")

                    if a_val:
                        success = await self._detail_page.fill_answer_by_metadata(matching_q, a_val)
                        if success:
                            filled_any = True
                            await self._detail_page.action_delay()

                # For chatbot flows, we submit immediately after filling to show next question
                if filled_any and await self._detail_page.is_chatbot_flow():
                    await self._detail_page.submit_application()
                elif not filled_any:
                    # If we couldn't fill anything new, break
                    break

                # Short delay for dynamic pages
                await asyncio.sleep(2)

            # Final validation check
            final_questions = await self._detail_page.extract_screening_questions()
            unanswered_required = []
            for q in final_questions:
                if q.get("required"):
                    val = (q.get("value") or "").strip()
                    is_unfilled = not val or val.lower() in ("select", "--select--", "choose")
                    if is_unfilled:
                        unanswered_required.append(q)

            if unanswered_required:
                logger.warning(
                    f"Validation: {len(unanswered_required)} required questions are still unanswered. Applying safe fallbacks..."
                )
                for q in unanswered_required:
                    fallback = self._generate_safe_fallback_for_question(q)
                    logger.info(
                        f"Last-ditch fallback: filling '{q.get('question')}' with '{fallback}'"
                    )
                    await self._detail_page.fill_answer_by_metadata(q, fallback)
                    await self._detail_page.action_delay()

                # Re-verify
                final_check = await self._detail_page.extract_screening_questions()
                still_empty = [
                    q
                    for q in final_check
                    if q.get("required")
                    and (
                        not q.get("value")
                        or q.get("value").lower() in ("select", "--select--", "choose")
                    )
                ]
                if still_empty:
                    logger.error(
                        f"Validation FAILED: Required questions still empty: {[q.get('question') for q in still_empty]}"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Failed in screening questions loop: {e}")
            return False
