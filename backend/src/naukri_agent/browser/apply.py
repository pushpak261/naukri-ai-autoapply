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

from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.core.interfaces import IQuestionAnswerer
from src.naukri_agent.utils.logger import get_logger, log_error, log_info, log_success, log_warning

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
            if is_external and self._settings.application.skip_external_apply:
                log_warning(f"External apply (skipped): {job.title}")
                return {
                    "status": ApplicationStatus.SKIPPED_EXTERNAL,
                    "error_message": "External application — skipped per config",
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

            await asyncio.sleep(2)

            # Step 5: Handle the apply flow (questions, confirmation, etc.)
            result = await self._handle_apply_flow(job)
            return result

        except Exception as e:
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

        # Check for immediate success
        if await self._detail_page.check_application_success():
            log_success(f"Applied successfully (direct): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Check for screening questions
        has_questions = await self._detail_page.detect_screening_questions()
        if has_questions:
            log_info("Screening questions detected — filling with AI...")
            answered = await self._fill_screening_questions(job)
            if not answered:
                log_warning("Could not fill all screening questions")

            # Submit after filling
            await self._detail_page.submit_application()
            await asyncio.sleep(2)

            if await self._detail_page.check_application_success():
                log_success(f"Applied successfully (with questions): {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Try submitting any visible form
        await self._detail_page.submit_application()
        await asyncio.sleep(3)

        # Final success check
        if await self._detail_page.check_application_success():
            log_success(f"Applied successfully: {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Check if already applied (post-click state)
        if await self._detail_page.is_already_applied():
            log_success(f"Application confirmed (already applied indicator): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # If we get here, we're not sure if the application went through
        log_warning(f"Application status uncertain: {job.title}")
        return {
            "status": ApplicationStatus.APPLIED,
            "error_message": "Status uncertain — could not confirm success indicator",
        }

    async def _fill_screening_questions(self, job: Job) -> bool:
        """
        Extract screening questions from the page and fill them using AI.

        Returns:
            True if questions were successfully filled.
        """
        try:
            # Collect questions from the page
            questions = await self._detail_page.extract_screening_questions()
            if not questions:
                logger.debug("No questions extracted from the page")
                return True  # No questions to fill

            # Get AI answers
            answers = await self._qa.answer_questions(questions, job)

            # Fill in the answers
            for answer_data in answers:
                question_text = answer_data.get("question", "")
                answer = answer_data.get("answer", "")
                confidence = answer_data.get("confidence", "low")

                if not answer or confidence == "low":
                    logger.warning(f"Skipping low-confidence answer for: {question_text}")
                    continue

                await self._detail_page.fill_answer(question_text, answer)
                await self._detail_page.action_delay()

            return True

        except Exception as e:
            logger.error(f"Failed to fill screening questions: {e}")
            return False
