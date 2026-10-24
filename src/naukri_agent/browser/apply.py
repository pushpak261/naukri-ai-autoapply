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
        applier = JobApplier(detail_page, settings, question_answerer)
        result = await applier.apply_to_job(job_data)
    """

    def __init__(
        self,
        detail_page: JobDetailPage,
        settings: Settings,
        question_answerer: IQuestionAnswerer,
        external_applier=None,
    ) -> None:
        self._detail_page = detail_page
        self._settings = settings
        self._qa = question_answerer
        self._external_applier = external_applier
        self._chatbot_managed = False
        self._chatbot_submission_uncertain = False

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
        apply_started = False
        try:
            from urllib.parse import urlsplit
            from src.naukri_agent.utils.helpers import extract_naukri_job_id
            current_url = self._detail_page._engine.page.url
            parsed = urlsplit(current_url)
            if parsed.scheme != "https" or parsed.hostname not in ("naukri.com", "www.naukri.com") or extract_naukri_job_id(current_url) != job.naukri_job_id:
                return {"status": ApplicationStatus.ERROR, "error_message": "The browser is not on the expected Naukri listing; no application was attempted."}
            # Step 1: Close any blocking popups/chatbots
            await self._detail_page.close_popups()
            await asyncio.sleep(1)

            # Step 2: Check if already applied
            already_applied = await self._detail_page.is_already_applied()
            if already_applied:
                # Naukri marks an employer-link click as Applied before the
                # employer receives anything. Resume only known external
                # destinations; the repository still guards submitted/uncertain jobs.
                if not self._settings.application.skip_external_apply and self._external_applier:
                    resolve = getattr(self._external_applier, "saved_destination", None)
                    cached = resolve(job) if resolve else None
                    if isinstance(cached, str) and cached:
                        return await self._external_applier.apply(self._detail_page._engine.page, cached, job)
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
                if not self._settings.application.skip_external_apply or getattr(self._settings.application, "collect_external_jobs", False):
                    external_url = await self._detail_page.get_external_apply_url()
                if not self._settings.application.skip_external_apply and self._external_applier:
                    if not external_url:
                        external_url = await self._detail_page.follow_external_apply_url()
                    return await self._external_applier.apply(self._detail_page._engine.page, external_url, job)
                return {
                    "status": ApplicationStatus.SKIPPED_EXTERNAL,
                    "error_message": "External employer form requires separate handling; no native application was submitted",
                    "external_url": external_url,
                }

            # Step 4: Find and click the Apply button
            log_info(f"Applying to: {job.title} @ {job.company}")

            apply_started = True
            apply_clicked = await self._detail_page.click_apply_button()
            if not apply_clicked:
                log_error("Could not find or click Apply button")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": "Apply button not found or not clickable",
                }

            # Wait for redirect/navigation (if any) or modal rendering
            with contextlib.suppress(Exception):
                await self._detail_page._interactions.wait_for_navigation_complete(timeout=5000)
            await asyncio.sleep(2)

            # Step 5: Handle the apply flow (questions, confirmation, etc.)
            result = await self._handle_apply_flow(job)
            if result.get("status") == ApplicationStatus.UNCERTAIN:
                # Naukri may finish on a post-apply page without a success
                # dialog. Read the original listing's authoritative Applied
                # state; never click Apply a second time to find out.
                await self._detail_page._engine.page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
                with contextlib.suppress(PlaywrightTimeoutError):
                    await self._detail_page._engine.page.locator("#already-applied, .already-applied").first.wait_for(state="visible", timeout=5000)
                confirmed_url = self._detail_page._engine.page.url
                confirmed_location = urlsplit(confirmed_url)
                if (confirmed_location.scheme == "https"
                    and confirmed_location.hostname in ("naukri.com", "www.naukri.com")
                    and extract_naukri_job_id(confirmed_url) == job.naukri_job_id
                    and await self._detail_page.is_already_applied()):
                    log_success(f"Applied successfully (confirmed on listing): {job.title} @ {job.company}")
                    return {"status": ApplicationStatus.APPLIED, "error_message": "Confirmed by the listing's Applied state after submission."}
            return result

        except (PlaywrightTimeoutError, PlaywrightError) as e:
            log_error(f"Application failed: {e}")
            logger.exception("Application error details")
            return {
                "status": ApplicationStatus.UNCERTAIN if apply_started else ApplicationStatus.ERROR,
                "error_message": 'Application state needs review after a connection error.' if apply_started else str(e),
            }

    async def _handle_apply_flow(self, job: Job) -> dict:
        """
        Handle the post-click apply flow, which may include:
        - Direct success (one-click apply)
        - Screening questions form
        - Chatbot-style Q&A
        - Resume upload prompt
        """
        self._chatbot_managed = False
        self._chatbot_submission_uncertain = False
        # Wait a moment for the apply modal/flow to appear
        await asyncio.sleep(2)

        # Check for early failure indicators
        failure_msg = await self._detail_page.check_application_failure()
        if failure_msg:
            if self._is_unanswered_questions_failure(failure_msg):
                if not getattr(
                    self._settings.application, "answer_questions_with_pdf", True
                ):
                    log_warning(
                        f"Screening questions/mandatory fields detected but 'answer_questions_with_pdf' is false. Skipping job: {job.title}"
                    )
                    return {
                        "status": ApplicationStatus.SKIPPED_SCREENING,
                        "error_message": f"Skipped: {failure_msg} and answer_questions_with_pdf is false",
                    }
                # If answer_questions_with_pdf is true, don't treat unanswered
                # questions as a failure — fall through to screening detection
                log_info("Mandatory fields detected — proceeding to fill screening questions")
            else:
                log_error(f"Application failed: {failure_msg}")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": f"Application rejected: {failure_msg}",
                }

        # Check for immediate success
        if await self._detail_page.check_application_success():
            log_success(f"Applied successfully (direct): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        submit_clicked = False
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

            log_info("Screening questions detected — filling from candidate evidence...")

            # Save-then-Submit loop: fill → save intermediate → submit → retry
            for submit_attempt in range(1):
                answered = await self._fill_screening_questions(job)
                if not answered:
                    if self._chatbot_submission_uncertain:
                        return {"status": ApplicationStatus.UNCERTAIN, "error_message": "Chatbot Save was clicked, but its result could not be verified. No second submission was attempted."}
                    log_warning("Could not fill all screening questions")
                    missing = "; ".join(getattr(self, "unanswered_questions", []))
                    return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": "Required screening answers need review: " + (missing or "Update the profile or review this form.")}

                if await self._detail_page.check_application_success():
                    return {"status": ApplicationStatus.APPLIED, "error_message": ""}

                if self._chatbot_managed:
                    # The chatbot runner owns Save and dynamic follow-ups.
                    # Only observe a receipt here; do not submit a second time.
                    submit_clicked = True
                    break

                # Let framework reactivity settle before submit
                await asyncio.sleep(1)

                # INTERMEDIATE SAVE: click Save/Next buttons (NOT Submit/Apply)
                # On Naukri, answers don't register until Save is clicked
                save_clicked = await self._detail_page.click_intermediate_save_button()
                if save_clicked:
                    logger.info("Clicked Save/Next button after filling questions")
                    await asyncio.sleep(1.5)
                    if await self._detail_page.check_application_success():
                        return {"status": ApplicationStatus.APPLIED, "error_message": ""}
                    # After Save, more questions might appear — try extracting
                    more_questions = await self._detail_page.extract_screening_questions()
                    unfilled = [
                        q for q in more_questions
                        if not (q.get("value") or "").strip()
                        or (q.get("value") or "").strip().lower() in ("select", "--select--", "choose")
                    ]
                    if unfilled:
                        logger.info(f"{len(unfilled)} more questions appeared after Save — filling them...")
                        if not await self._fill_screening_questions(job):
                            return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": "Additional required screening answers need review."}
                        await asyncio.sleep(1)
                        # Re-save after filling new questions
                        await self._detail_page.click_intermediate_save_button()
                        await asyncio.sleep(0.5)
                else:
                    logger.debug("No Save/Next button found on page")

                # Trigger blur on all filled fields to ensure validation fires before submit
                await self._detail_page._trigger_form_validation()

                # Submit
                submit_clicked = await self._detail_page.submit_application()
                await asyncio.sleep(2)

                # Check for failure indicators
                failure_msg = await self._detail_page.check_application_failure()
                if not failure_msg:
                    # No failure — check success and proceed
                    if await self._detail_page.check_application_success():
                        log_success(f"Applied successfully (with questions): {job.title}")
                        return {"status": ApplicationStatus.APPLIED, "error_message": ""}
                    break

                if not self._is_unanswered_questions_failure(failure_msg):
                    log_error(f"Application failed: {failure_msg}")
                    return {
                        "status": ApplicationStatus.FAILED,
                        "error_message": f"Application rejected: {failure_msg}",
                    }

                return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": f"The platform rejected screening values: {failure_msg}. Review before retrying."}

            # Final state checks after retry loop
            if await self._detail_page.check_application_success():
                log_success(f"Applied successfully (with questions): {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}

            # For chatbot flows, make one final explicit Save attempt
            if not submit_clicked and await self._detail_page.is_chatbot_flow():
                logger.info("Final chatbot Save attempt after screening loop...")
                final_save = await self._detail_page.click_chatbot_save_button()
                if final_save:
                    submit_clicked = True
                    await asyncio.sleep(2)
                    if await self._detail_page.check_application_success():
                        log_success(f"Applied successfully (chatbot final save): {job.title}")
                        return {"status": ApplicationStatus.APPLIED, "error_message": ""}

            failure_msg = await self._detail_page.check_application_failure()
            if failure_msg:
                log_error(f"Application failed: {failure_msg}")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": f"Application rejected: {failure_msg}",
                }

        # Do not re-click after a submit attempt or when the native form has disappeared.
        if not submit_clicked and await self._detail_page._is_apply_modal_visible():
            submit_clicked = await self._detail_page.submit_application()

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
        # Use state-change detection as a fallback:

        # 3. Button text now says "Applied"
        if await self._detail_page.is_already_applied():
            log_success(f"Application confirmed (button changed): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # 4. If we clicked submit and no failure, wait briefly and recheck
        if submit_clicked:
            await asyncio.sleep(2)
            if await self._detail_page.check_application_success():
                log_success(f"Applied successfully (delayed confirmation): {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}
            if await self._detail_page.is_already_applied():
                log_success(f"Application confirmed (delayed button check): {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}
        # 5. If answer_questions_with_pdf is False and a form is still visible → screening form we couldn't parse
        if not getattr(self._settings.application, "answer_questions_with_pdf", True):
            log_warning(
                f"Unsubmitted form detected but 'answer_questions_with_pdf' is false. Skipping job: {job.title}"
            )
            return {
                "status": ApplicationStatus.SKIPPED_SCREENING,
                "error_message": "Skipped: Unsubmitted form detected and answer_questions_with_pdf is false",
            }

        logger.info("No receipt in the apply view; checking the original listing: %s", job.title)
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
        from libs.common.screening import evidence_answer, format_evidence, question_key
        verified = getattr(self, "_verified_screening_answers", {}).get(question_key(question.get("question", "")))
        if verified:
            return format_evidence(verified, question, experience_in_years=False)
        return evidence_answer(question, self._settings, getattr(self._qa, '_profile', None))

    async def _fill_screening_questions(self, job: Job) -> bool:
        """
        Extract, answer, and fill screening questions iteratively.
        Handles dynamic follow-up questions and validates mandatory fields.
        Optimized to avoid wasting AI tokens on questions that resolve
        deterministically or don't change between iterations.
        Uses JS-based force fill as a last-resort when DOM selectors fail.
        """
        self.unanswered_questions = []
        self._verified_screening_answers = {}
        try:
            chatbot = getattr(self._detail_page, "is_chatbot_flow", None)
            if chatbot and await chatbot() is True:
                from src.naukri_agent.browser.screening_chatbot import fill_chatbot
                self._chatbot_managed = True
                return await fill_chatbot(self, job)
            max_attempts = 8
            attempt = 0
            seen_questions: set[tuple[str, str]] = set()
            last_unfilled_count = 0
            stale_iterations = 0
            last_question_texts: frozenset[str] = frozenset()

            while attempt < max_attempts:
                attempt += 1
                logger.info(f"Screening questions fill attempt {attempt}/{max_attempts}...")

                # Extract questions
                questions = await self._detail_page.extract_screening_questions()

                # When JS extraction fails/returns empty, try Playwright fallback detection
                if not questions:
                    logger.debug("No screening questions found via JS engine. Trying Playwright fallback...")
                    questions = await self._detect_questions_via_playwright()
                    if not questions:
                        if await self._detail_page._is_apply_modal_visible() is True:
                            self.unanswered_questions = ["The active screening form could not be read"]
                            return False
                        logger.info("No screening fields remain; waiting for a platform receipt.")
                        return True

                # Filter for unfilled fields
                unfilled_questions = []
                for q in questions:
                    if q.get("type") == "file":
                        if q.get("value"):
                            continue
                        import re
                        from src.naukri_agent.utils.helpers import resolve_path_within
                        label = str(q.get("question", ""))
                        selected = resolve_path_within(self._settings.resume.path, self._settings.resumes_dir)
                        is_resume = re.search(r"\b(?:resume|rÃ©sumÃ©|cv)\b", label, re.I)
                        uploaded = bool(is_resume and selected and selected.is_file() and await self._detail_page.upload_resume_file(q, str(selected)))
                        if not uploaded and q.get("required", True):
                            from libs.common.screening_review import ScreeningReviewStore
                            await asyncio.to_thread(ScreeningReviewStore(self._settings.project_root).remember, q, job)
                            self.unanswered_questions.append(label + " (attachment requires review)")
                            return False
                        continue
                    val = (q.get("value") or "").strip()
                    is_unfilled = not val or val.lower() in ("select", "--select--", "choose")
                    if is_unfilled:
                        q_text = q.get("question", "").strip()
                        # Fix empty question text: infer from options or container metadata
                        if not q_text:
                            options = q.get("options", [])
                            if options:
                                q_text = options[0].get("text", "")
                            else:
                                q_text = q.get("original_question", "") or q.get("id", "Question")
                            q["question"] = q_text
                        unfilled_questions.append(q)

                if not unfilled_questions:
                    logger.info("All screening questions are filled.")
                    break

                current_unfilled = len(unfilled_questions)
                current_question_texts = frozenset(
                    q.get("question", "") for q in unfilled_questions
                )
                if current_unfilled == last_unfilled_count:
                    if current_question_texts != last_question_texts:
                        # Question text changed — chatbot advanced to a new question
                        logger.debug("Question text changed, resetting stale counter")
                        stale_iterations = 0
                    else:
                        stale_iterations += 1
                else:
                    stale_iterations = 0
                last_unfilled_count = current_unfilled
                last_question_texts = current_question_texts

                if stale_iterations >= 2:
                    logger.info(
                        f"Unfilled question count unchanged for {stale_iterations} iterations. "
                        "Falling back to safe defaults without AI."
                    )
                    for q in unfilled_questions:
                        fallback = self._generate_safe_fallback_for_question(q)
                        if fallback:
                            success = await self._detail_page.fill_answer_by_metadata(q, fallback)
                            if not success:
                                logger.warning(
                                    f"Fill failed for '{q.get('question')}', trying JS force fill..."
                                )
                                await self._force_fill_single_question(q, fallback)
                            await self._detail_page.action_delay()
                    break

                # Skip questions we've already tried (waste of AI tokens)
                fresh_questions = [
                    q
                    for q in unfilled_questions
                    if (str(q.get("id", "")), str(q.get("question", ""))) not in seen_questions
                ]
                if not fresh_questions:
                    logger.info(
                        "All unfilled questions previously attempted. Using safe fallbacks."
                    )
                    all_filled = True
                    for q in unfilled_questions:
                        fallback = self._generate_safe_fallback_for_question(q)
                        if fallback:
                            success = await self._detail_page.fill_answer_by_metadata(q, fallback)
                            if not success:
                                logger.warning(
                                    f"Fill failed for '{q.get('question')}', trying JS force fill..."
                                )
                                js_ok = await self._force_fill_single_question(q, fallback)
                                if not js_ok:
                                    all_filled = False
                            await self._detail_page.action_delay()
                    if all_filled:
                        break
                    # If fills still failing, try final JS force fill and exit
                    await self._force_fill_all_required_via_js()
                    break

                for q in fresh_questions:
                    seen_questions.add((str(q.get("id", "")), str(q.get("question", ""))))

                logger.info(
                    f"Found {len(unfilled_questions)} unfilled questions "
                    f"({len(fresh_questions)} new). Generating answers..."
                )

                # Answer them (only fresh ones)
                answers = await self._qa.answer_questions(fresh_questions, job)

                # Offline completion is explicit: even optional text questions
                # requested by the recruiter must have an answer before Save.
                if not self._settings.ai.use_gemini:
                    unresolved = [answer.get("question", "Unlabelled question") for answer in answers
                                  if not str(answer.get("answer", "")).strip()
                                  or answer.get("confidence") in ("low", "unknown", "needs_input")]
                    answered_keys = {(answer.get("id"), answer.get("question")) for answer in answers}
                    unresolved.extend(q.get("question", "Unlabelled question") for q in fresh_questions
                                      if (q.get("id"), q.get("question")) not in answered_keys)
                    if unresolved:
                        self.unanswered_questions.extend(dict.fromkeys(unresolved))
                        return False

                from libs.common.screening import question_key
                self._verified_screening_answers.update({question_key(answer.get("question", "")): answer["answer"]
                    for answer in answers if answer.get("answer") and answer.get("confidence") not in ("low", "unknown", "needs_input")})

                filled_any = False
                for ans in answers:
                    q_text = ans.get("question", "")
                    q_id = ans.get("id") or ""
                    a_val = str(ans.get("answer", "")).strip()
                    if ans.get("confidence") in ("low", "unknown", "needs_input"):
                        a_val = ""

                    # Find matching question in unfilled
                    matching_q = next(
                        (
                            uq
                            for uq in unfilled_questions
                            if (q_id and uq.get("id") == q_id)
                            or (q_text and uq.get("question") == q_text)
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
                            logger.debug(f"Successfully filled '{q_text}' with '{a_val[:50]}'")
                        else:
                            logger.warning(
                                f"AI/fallback fill failed for '{q_text}', trying JS force fill..."
                            )
                            js_ok = await self._force_fill_single_question(matching_q, a_val)
                            if js_ok:
                                filled_any = True
                            await self._detail_page.action_delay()
                # For chatbot flows, click the chatbot Save button to submit/advance
                if filled_any and await self._detail_page.is_chatbot_flow():
                    save_ok = await self._detail_page.click_chatbot_save_button()
                    if save_ok:
                        logger.info("Chatbot: clicked Save after filling questions")
                        await asyncio.sleep(1.5)
                    else:
                        logger.warning("Chatbot answer could not be saved; leaving the form for review.")
                        return False
                elif not filled_any:
                    break

                # Try clicking Save button after each fill iteration.
                # Naukri's screening form requires Save to register answers.
                if filled_any and not await self._detail_page.is_chatbot_flow():
                    save_clicked = await self._detail_page.click_intermediate_save_button()
                    if save_clicked:
                        logger.debug("Clicked Save after fill iteration")
                        await asyncio.sleep(1)

                await asyncio.sleep(1.5)

            # ---- Final validation with retry and JS force fill ----
            final_questions = await self._detail_page.extract_screening_questions()
            unanswered_required = [
                q
                for q in final_questions
                if (q.get("required", q.get("is_required", True)) or (not self._settings.ai.use_gemini and q.get("type") != "file"))
                and (
                    not (q.get("value") or "").strip()
                    or (q.get("value") or "").strip().lower() in ("select", "--select--", "choose")
                )
            ]

            if unanswered_required:
                logger.warning(
                    f"Validation: {len(unanswered_required)} required questions still unanswered. "
                    "Applying safe fallbacks..."
                )
                for q in unanswered_required:
                    fallback = self._generate_safe_fallback_for_question(q)
                    if not fallback:
                        from libs.common.screening_review import ScreeningReviewStore
                        await asyncio.to_thread(ScreeningReviewStore(self._settings.project_root).remember, q, job)
                        self.unanswered_questions.append(q.get("question", "Unlabelled required field"))
                        return False
                    logger.info(
                        f"Last-ditch fallback: filling '{q.get('question')}' with '{fallback}'"
                    )
                    success = await self._detail_page.fill_answer_by_metadata(q, fallback)
                    if not success:
                        logger.warning(
                            f"Fallback metadata fill failed for '{q.get('question')}', JS force fill..."
                        )
                        await self._force_fill_single_question(q, fallback)
                    await self._detail_page.action_delay()

                # Re-check after fallback fills
                final_check = await self._detail_page.extract_screening_questions()
                still_empty = [
                    q
                    for q in final_check
                    if (q.get("required", q.get("is_required", True)) or (not self._settings.ai.use_gemini and q.get("type") != "file"))
                    and (
                        not (q.get("value") or "").strip()
                        or (q.get("value") or "").strip().lower()
                        in ("select", "--select--", "choose")
                    )
                ]
                if still_empty:
                    logger.warning(
                        f"Validation: {len(still_empty)} required questions still empty. "
                        "Running JS force fill for all remaining..."
                    )
                    await self._force_fill_all_required_via_js()

                    # Final re-check after JS force fill
                    final_check2 = await self._detail_page.extract_screening_questions()
                    still_empty2 = [
                        q
                        for q in final_check2
                        if (q.get("required", q.get("is_required", True)) or (not self._settings.ai.use_gemini and q.get("type") != "file"))
                        and (
                            not (q.get("value") or "").strip()
                            or (q.get("value") or "").strip().lower()
                            in ("select", "--select--", "choose")
                        )
                    ]
                    if still_empty2:
                        logger.error(
                            f"Validation FAILED: Required questions still empty: "
                            f"{[q.get('question') for q in still_empty2]}"
                        )
                        return False

            return True

        except PlaywrightError:
            raise
        except Exception as e:
            logger.error(f"Failed in screening questions loop: {e}")
            return False

    async def _force_fill_single_question(self, question: dict, answer: str) -> bool:
        """Force-fill a single question using JS direct DOM manipulation as last resort."""
        page = self._detail_page._engine.page
        q_text = question.get("question", "")
        q_type = question.get("type", "text")
        options = question.get("options", [])
        answer_str = str(answer).strip()

        try:
            if q_type in ("radio", "checkbox"):
                # JS-based checkbox/radio fill
                result = await page.evaluate(
                    r"""({ answer, qText, options }) => {
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
                        const al = answer.toLowerCase().trim();
                        const ql = qText.toLowerCase().trim();

                        // Try finding by label text matching question
                        const allLabels = document.querySelectorAll('label');
                        for (const lbl of allLabels) {
                            const lt = (lbl.innerText || '').trim().toLowerCase();
                            if (!lt) continue;
                            if (ql && (lt.includes(ql) || ql.includes(lt))) {
                                const inp = lbl.querySelector('input[type="radio"], input[type="checkbox"]');
                                if (inp) {
                                    if (!inp.checked) {
                                        inp.click();
                                        inp.checked = true;
                                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    return true;
                                }
                                // Custom toggle inside label
                                lbl.click();
                                return true;
                            }
                        }

                        // Try finding by answer text matching
                        for (const lbl of allLabels) {
                            const lt = (lbl.innerText || '').trim().toLowerCase();
                            if (lt === al || lt.includes(al) || al.includes(lt)) {
                                const inp = lbl.querySelector('input[type="radio"], input[type="checkbox"]');
                                if (inp) {
                                    if (!inp.checked) {
                                        inp.click();
                                        inp.checked = true;
                                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    return true;
                                }
                                lbl.click();
                                return true;
                            }
                        }

                        // Try visible toggle/switch elements
                        const toggles = document.querySelectorAll(
                            '[role="switch"], [class*="toggle" i], [class*="switch" i]'
                        );
                        for (const tg of toggles) {
                            const tt = (tg.innerText || tg.textContent || '').trim().toLowerCase();
                            if (ql && (tt.includes(ql) || ql.includes(tt))) {
                                const isOn = tg.getAttribute('aria-checked') === 'true' || tg.classList.contains('active');
                                const shouldBeOn = al === 'yes' || al === 'true' || al === '1' || al === 'y';
                                if (isOn !== shouldBeOn) {
                                    tg.click();
                                    tg.setAttribute('aria-checked', shouldBeOn ? 'true' : 'false');
                                    tg.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                                return true;
                            }
                        }

                        // Absolute last resort: find first visible unchecked radio/checkbox in apply area
                        const applyArea = document.querySelector(
                            '[class*="apply-modal"], [class*="apply-form"], [class*="chatbot"], ' +
                            '[class*="modal" i], form, body'
                        );
                        const inputs = (applyArea || document).querySelectorAll(
                            'input[type="radio"]:not([style*="display: none"]), ' +
                            'input[type="checkbox"]:not([style*="display: none"])'
                        );
                        for (const inp of inputs) {
                            if (inp.offsetParent !== null && !inp.checked) {
                                inp.click();
                                inp.checked = true;
                                inp.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            }
                        }
                        return false;
                    }""",
                    {"answer": answer_str, "qText": q_text, "options": options}
                )
                return result

            else:
                # Text/number/date/dropdown JS force fill
                result = await page.evaluate(
                    r"""({ answer, qText }) => {
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
                        const ans = String(answer);
                        const ql = qText.toLowerCase().trim();

                        // 1. Find by label text
                        const labels = document.querySelectorAll('label');
                        for (const lbl of labels) {
                            const lt = (lbl.innerText || '').trim().toLowerCase();
                            if (!lt) continue;
                            if (ql && (lt.includes(ql) || ql.includes(lt))) {
                                const forId = lbl.getAttribute('for');
                                if (forId) {
                                    const inp = document.getElementById(forId);
                                    if (inp) {
                                        const tag = inp.tagName.toLowerCase();
                                        if (tag === 'select') {
                                            const opt = Array.from(inp.options).find(o =>
                                                o.text.toLowerCase() === ans.toLowerCase() ||
                                                o.value.toLowerCase() === ans.toLowerCase()
                                            );
                                            if (opt) { inp.value = opt.value; } else { return false; }

                                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                                            return true;
                                        }
                                        const nativeSetter = Object.getOwnPropertyDescriptor(
                                            window.HTMLInputElement.prototype, 'value'
                                        ).set;
                                        inp.focus();
                                        nativeSetter.call(inp, '');
                                        nativeSetter.call(inp, ans);
                                        inp.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                                        inp.blur();
                                        inp.dispatchEvent(new Event('blur', { bubbles: true }));
                                        return true;
                                    }
                                }
                                // Search inside label
                                const inp = lbl.querySelector('input, select, textarea');
                                if (inp) {
                                    if (inp.tagName.toLowerCase() === 'select') {
                                        const opt = Array.from(inp.options).find(o =>
                                            o.text.toLowerCase() === ans.toLowerCase() ||
                                            o.value.toLowerCase() === ans.toLowerCase()
                                        );
                                        if (opt) { inp.value = opt.value; } else { return false; }

                                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                                        return true;
                                    }
                                    const nativeSetter = Object.getOwnPropertyDescriptor(
                                        window.HTMLInputElement.prototype, 'value'
                                    ).set;
                                    inp.focus();
                                    nativeSetter.call(inp, '');
                                    nativeSetter.call(inp, ans);
                                    inp.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                                    inp.blur();
                                    inp.dispatchEvent(new Event('blur', { bubbles: true }));
                                    return true;
                                }
                            }
                        }

                        // 2. Find by placeholder text
                        const inputs = document.querySelectorAll(
                            'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"]):not([type="file"]), ' +
                            'select, textarea'
                        );
                        for (const inp of inputs) {
                            if (inp.offsetParent === null) continue;
                            const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
                            if (ph && (ql.includes(ph) || ph.includes(ql))) {
                                if (inp.tagName.toLowerCase() === 'select') {
                                    const opt = Array.from(inp.options).find(o =>
                                        o.text.toLowerCase() === ans.toLowerCase() ||
                                        o.value.toLowerCase() === ans.toLowerCase()
                                    );
                                    if (opt) { inp.value = opt.value; } else { return false; }

                                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                                    return true;
                                }
                                const nativeSetter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value'
                                ).set;
                                inp.focus();
                                nativeSetter.call(inp, '');
                                nativeSetter.call(inp, ans);
                                inp.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                                inp.dispatchEvent(new Event('change', { bubbles: true }));
                                inp.blur();
                                inp.dispatchEvent(new Event('blur', { bubbles: true }));
                                return true;
                            }
                        }

                        return false;
                    }""",
                    {"answer": answer_str, "qText": q_text}
                )
                return result
        except Exception as e:
            logger.debug(f"JS force fill failed for '{q_text}': {e}")
            return False

    async def _force_fill_all_required_via_js(self) -> None:
        """Never populate unidentified required fields with invented defaults."""
        logger.warning('Unanswered required fields need profile evidence; generic autofill is disabled.')

    async def _detect_questions_via_playwright(self) -> list[dict]:
        """
        Fallback question detection using Playwright-native selectors.
        Used when JS-based extraction fails or returns empty.
        Scans for labels with associated inputs in the visible DOM.
        """
        page = self._detail_page._engine.page
        questions = []
        seen_texts: set[str] = set()
        field_index = 0

        try:
            # Find the apply form container
            form_selectors = [
                '[class*="apply-modal"]',
                '[class*="apply-form"]',
                '[class*="chatbot"]',
                '[class*="modal" i]',
                '[class*="popup" i]',
                'form',
            ]
            form_container = None
            for sel in form_selectors:
                try:
                    container = await page.query_selector(sel)
                    if container and await container.is_visible():
                        form_container = container
                        break
                except Exception:
                    continue

            # Find all visible labels inside the form
            if form_container:
                labels = await form_container.query_selector_all("label")
            else:
                labels = await page.query_selector_all("label")

            for label in labels:
                try:
                    if not await label.is_visible():
                        continue
                    label_text = (await label.text_content() or "").strip()
                    if not label_text or len(label_text) < 3:
                        continue
                    if label_text.lower() in seen_texts or any(
                        skip in label_text.lower()
                        for skip in ["deselect", "remove", "upload", "attach"]
                    ):
                        continue

                    label_for = await label.get_attribute("for")
                    input_elem = None

                    if label_for:
                        input_elem = await page.query_selector(f"#{label_for}")
                    if not input_elem:
                        input_elem = await label.query_selector("input, select, textarea")

                    if not input_elem:
                        continue

                    tag = await input_elem.evaluate("el => el.tagName.toLowerCase()")
                    input_type = await input_elem.evaluate(
                        "el => (el.getAttribute('type') || 'text').toLowerCase()"
                    )
                    current_value = await input_elem.evaluate("el => el.value || ''")
                    is_required = await input_elem.evaluate(
                        "el => el.hasAttribute('required') || el.getAttribute('aria-required') === 'true'"
                    )

                    q_type = "text"
                    if tag == "select":
                        q_type = "dropdown"
                    elif tag == "textarea":
                        q_type = "text_area"
                    elif input_type == "radio":
                        q_type = "radio"
                    elif input_type == "checkbox":
                        q_type = "checkbox"
                    elif input_type == "file":
                        q_type = "file"
                    elif input_type == "number":
                        q_type = "number"

                    # For radio/checkbox, collect options
                    options = []
                    if q_type in ("radio", "checkbox"):
                        name = await input_elem.get_attribute("name")
                        if name:
                            siblings = await page.query_selector_all(
                                f'input[type="{input_type}"][name="{name}"]'
                            )
                            for sib in siblings:
                                sib_label = await self._find_label_for_input(page, sib)
                                sib_text = sib_label or await sib.get_attribute("value") or ""
                                if sib_text:
                                    options.append({"text": sib_text.strip(), "value": sib_text.strip()})

                    # For dropdown, collect options
                    if q_type == "dropdown":
                        option_elems = await input_elem.query_selector_all("option")
                        for opt in option_elems:
                            try:
                                opt_text = (await opt.text_content() or "").strip()
                                opt_val = await opt.get_attribute("value") or ""
                                if opt_text and opt_text.lower() not in ("select", "--select--", "choose"):
                                    options.append({"text": opt_text, "value": opt_val or opt_text})
                            except Exception:
                                continue

                    field_id = f"pw_fallback_{field_index}"
                    field_index += 1
                    seen_texts.add(label_text.lower())

                    questions.append({
                        "id": field_id,
                        "question": label_text,
                        "type": q_type,
                        "options": options,
                        "required": is_required,
                        "value": current_value,
                    })
                except Exception:
                    continue

            if questions:
                logger.info(f"Playwright fallback detected {len(questions)} questions")

        except Exception as e:
            logger.debug(f"Playwright fallback detection failed: {e}")

        return questions

    async def _find_label_for_input(self, page, input_elem) -> str | None:
        """Find label text for a given input element."""
        try:
            input_id = await input_elem.get_attribute("id")
            if input_id:
                label_elem = await page.query_selector(f'label[for="{input_id}"]')
                if label_elem:
                    return (await label_elem.text_content() or "").strip()
            parent_label = await input_elem.evaluate("el => el.closest('label')")
            if parent_label:
                return (await input_elem.evaluate("el => el.closest('label').innerText") or "").strip()
        except Exception:
            pass
        return None
