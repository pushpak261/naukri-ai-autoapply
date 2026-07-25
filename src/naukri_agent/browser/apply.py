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
                if not getattr(self._settings.application, "skip_external_apply", True):
                    log_info(f"Attempting external apply: {job.title} @ {job.company}")
                    apply_clicked = await self._detail_page.click_external_apply_button()
                    if apply_clicked:
                        try:
                            await self._detail_page._interactions.wait_for_navigation_complete(timeout=15000)
                        except Exception:
                            pass
                        await asyncio.sleep(3)
                        if await self._detail_page.is_external_apply_successful():
                            log_info(f"External apply assumed successful: {job.title}")
                            return {
                                "status": ApplicationStatus.APPLIED,
                                "error_message": "",
                            }
                        result = await self._handle_apply_flow(job)
                        return result
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

            # Save-then-Submit loop: fill → save intermediate → submit → retry
            for submit_attempt in range(3):
                answered = await self._fill_screening_questions(job)
                if not answered:
                    log_warning("Could not fill all screening questions")

                # Let framework reactivity settle before submit
                await asyncio.sleep(1)

                # INTERMEDIATE SAVE: click Save/Next buttons (NOT Submit/Apply)
                # On Naukri, answers don't register until Save is clicked
                save_clicked = await self._detail_page.click_intermediate_save_button()
                if save_clicked:
                    logger.info("Clicked Save/Next button after filling questions")
                    await asyncio.sleep(1.5)
                    # After Save, more questions might appear — try extracting
                    more_questions = await self._detail_page.extract_screening_questions()
                    unfilled = [
                        q for q in more_questions
                        if not (q.get("value") or "").strip()
                        or (q.get("value") or "").strip().lower() in ("select", "--select--", "choose")
                    ]
                    if unfilled:
                        logger.info(f"{len(unfilled)} more questions appeared after Save — filling them...")
                        await self._fill_screening_questions(job)
                        await asyncio.sleep(1)
                        # Re-save after filling new questions
                        await self._detail_page.click_intermediate_save_button()
                        await asyncio.sleep(0.5)
                else:
                    logger.debug("No Save/Next button found on page")

                # Trigger blur on all filled fields to ensure validation fires before submit
                await self._detail_page._trigger_form_validation()

                # Submit
                await self._detail_page.submit_application()
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

                logger.warning(
                    f"Submit attempt {submit_attempt + 1}/3 triggered validation error. "
                    "Re-filling and retrying..."
                )
                # Force-fill via JS as retry strategy
                await self._force_fill_all_required_via_js()
                await asyncio.sleep(1)

            # Final state checks after retry loop
            if await self._detail_page.check_application_success():
                log_success(f"Applied successfully (with questions): {job.title}")
                return {"status": ApplicationStatus.APPLIED, "error_message": ""}

            # For chatbot flows, make one final explicit Save attempt
            if await self._detail_page.is_chatbot_flow():
                logger.info("Final chatbot Save attempt after screening loop...")
                final_save = await self._detail_page.click_chatbot_save_button()
                if final_save:
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

        # Try submitting any visible form
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

        # 1. Apply modal is gone → application was processed (modal closed after submit)
        if not await self._detail_page._is_apply_modal_visible():
            log_success(f"Application assumed successful (modal closed): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # 2. Apply button is no longer clickable → it changed to "Applied" state
        if not await self._detail_page._is_apply_button_present():
            log_success(f"Application confirmed (apply button gone): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

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
            if not await self._detail_page._is_apply_modal_visible():
                log_success(f"Application assumed successful (modal closed after delay): {job.title}")
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

        is_exp_q = any(kw in q_text for kw in ["experience", "years", "month", "exp", "how many"])
        if q_type in ("radio", "dropdown", "checkbox"):
            if is_exp_q:
                return pick_option(["1 year", "1-2", "0-1", "1"], options[0] if options else "1 year")
            if "reloc" in q_text or "travel" in q_text or "shift" in q_text or "agree" in q_text or "consent" in q_text or "resid" in q_text:
                return pick_option(["yes", "agree", "true", "y"], "Yes")
            if "notice" in q_text:
                return pick_option(["immediate", "0 days", "15 days", "serving"], "Immediate")
            if "gender" in q_text:
                return pick_option(["male"], "Male")
            if "ctc" in q_text or "salary" in q_text:
                return pick_option(["4", "5", "6"], options[0] if options else "6 LPA")
            if "location" in q_text or "city" in q_text:
                return pick_option(["pune"], "Pune")
            return pick_option(["yes", "agree", "true", "y"], options[0] if options else "Yes")
        else:
            # Text / number / date fields
            if is_exp_q:
                return "1" if (q_type == "number" or "digit" in q_text) else "1 year"
            if "ctc" in q_text or "salary" in q_text:
                if "expected" in q_text:
                    return (
                        "600000"
                        if "rupee" in q_text or "rs" in q_text or "annual" in q_text
                        else "6 LPA"
                    )
                return (
                    "450000" if "rupee" in q_text or "rs" in q_text or "annual" in q_text else "4.5 LPA"
                )
            if "notice" in q_text:
                return "Immediate"
            if "location" in q_text or "city" in q_text:
                return "Pune"
            if "phone" in q_text or "mobile" in q_text:
                return self._settings.naukri.mobile_number or "9999999999"
            if "email" in q_text:
                return self._settings.naukri.email or "candidate@example.com"
            if "name" in q_text:
                return getattr(self._settings.naukri, "name", "") or "Candidate"
            if "why" in q_text or "join" in q_text or "fit" in q_text:
                return "I have 1 year of hands-on experience in Java, Spring Boot, and React. I build scalable microservices and deliver high-quality code efficiently."
            if "project" in q_text or "describe" in q_text:
                return "I developed full-stack web applications and microservices using Spring Boot, React, and MySQL, with automated CI/CD deployment."
            return "Yes"

    async def _fill_screening_questions(self, job: Job) -> bool:
        """
        Extract, answer, and fill screening questions iteratively.
        Handles dynamic follow-up questions and validates mandatory fields.
        Optimized to avoid wasting AI tokens on questions that resolve
        deterministically or don't change between iterations.
        Uses JS-based force fill as a last-resort when DOM selectors fail.
        """
        try:
            max_attempts = 8
            attempt = 0
            seen_questions: set[str] = set()
            last_unfilled_count = 0
            stale_iterations = 0

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
                        logger.debug("No screening questions detected via any method.")
                        # Don't break — let force-fill handle any remaining fields
                        if attempt >= 2:
                            logger.warning("Giving up on question detection. Running force fill for all visible fields.")
                            await self._force_fill_all_required_via_js()
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

                current_unfilled = len(unfilled_questions)
                if current_unfilled == last_unfilled_count:
                    stale_iterations += 1
                else:
                    stale_iterations = 0
                last_unfilled_count = current_unfilled

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
                    if (q.get("id") or q.get("question", "")) not in seen_questions
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
                    qid = q.get("id") or q.get("question", "")
                    if qid:
                        seen_questions.add(qid)

                logger.info(
                    f"Found {len(unfilled_questions)} unfilled questions "
                    f"({len(fresh_questions)} new). Generating answers..."
                )

                # Answer them (only fresh ones)
                answers = await self._qa.answer_questions(fresh_questions, job)

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
                            if (q_id and uq.get("id") == q_id)
                            or (q_text and uq.get("question") == q_text)
                            or (
                                q_text
                                and uq.get("question")
                                and (
                                    q_text.lower() in uq.get("question", "").lower()
                                    or uq.get("question", "").lower() in q_text.lower()
                                )
                            )
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
                        # Verify Save was effective — check if Save button is still visible
                        # If still there, retry the click
                        for retry_click in range(2):
                            still_has_save = await self._detail_page._engine.page.evaluate(
                                r"""() => {
                                    const btns = document.querySelectorAll('button, [role="button"], a');
                                    for (const btn of btns) {
                                        const text = (btn.textContent || btn.innerText || '').trim().toLowerCase();
                                        if (text === 'save' || text.startsWith('save ') || text.startsWith('save&')) {
                                            const style = window.getComputedStyle(btn);
                                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                                const rect = btn.getBoundingClientRect();
                                                if (rect.width > 15 && rect.height > 15) return true;
                                            }
                                        }
                                    }
                                    return false;
                                }"""
                            )
                            if not still_has_save:
                                break
                            logger.warning(
                                f"Chatbot Save button still visible after click (retry {retry_click + 1}/2). Re-clicking..."
                            )
                            await self._detail_page.click_chatbot_save_button()
                            await asyncio.sleep(1.5)
                    else:
                        # Fallback to generic submit if chatbot Save not found
                        await self._detail_page.submit_application()
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
                if q.get("required")
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
                    if q.get("required")
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
                        if q.get("required")
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
                                            if (opt) { inp.value = opt.value; }
                                            else if (inp.options.length > 0) { inp.value = inp.options[0].value; }
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
                                        if (opt) { inp.value = opt.value; }
                                        else if (inp.options.length > 0) { inp.value = inp.options[0].value; }
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
                                    if (opt) { inp.value = opt.value; }
                                    else if (inp.options.length > 0) { inp.value = inp.options[0].value; }
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

                        // 3. Find any visible empty input (last resort)
                        for (const inp of inputs) {
                            if (inp.offsetParent === null) continue;
                            const val = (inp.value || '').trim();
                            if (val === '' || val === 'Select' || val === '--Select--') {
                                if (inp.tagName.toLowerCase() === 'select') {
                                    if (inp.options.length > 0) { inp.value = inp.options[0].value; }
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

    async def _force_fill_all_required_via_js(self) -> bool:
        """
        Ultimate fallback: use JS to find ALL empty required form fields
        and fill them with sensible defaults, directly manipulating DOM values.
        """
        page = self._detail_page._engine.page
        try:
            # Build profile-based defaults
            default_ctc = self._settings.profile.current_ctc or "440000"
            default_exp = self._settings.profile.total_experience or "1"
            default_notice = self._settings.profile.notice_period or "Immediate"
            default_location = self._settings.profile.current_location or "Pune"

            result = await page.evaluate(
                r"""({ defaultCtc, defaultExp, defaultNotice, defaultLocation }) => {
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
                    const applyArea = document.querySelector(
                        '[class*="apply-modal"], [class*="apply-form"], [class*="chatbot"], ' +
                        '[class*="modal" i], form, body'
                    ) || document;
                    let filled = 0;

                    // Fill selects
                    const selects = applyArea.querySelectorAll('select:not([style*="display: none"])');
                    for (const sel of selects) {
                        if (sel.offsetParent === null) continue;
                        const val = (sel.value || '').trim();
                        if (!val || val === 'Select' || val === '--Select--') {
                            if (sel.options.length > 0) {
                                // Skip first placeholder option
                                let chosen = false;
                                for (let i = 1; i < sel.options.length; i++) {
                                    const opt = sel.options[i];
                                    const ot = opt.text.toLowerCase();
                                    if (ot.includes('immediate') || ot.includes('0 day') || ot.includes('yes') || ot.includes('male')) {
                                        sel.value = opt.value;
                                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                                        filled++;
                                        chosen = true;
                                        break;
                                    }
                                }
                                if (!chosen && sel.options.length > 1) {
                                    sel.value = sel.options[1].value;
                                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                                    filled++;
                                } else if (!chosen && sel.options.length === 1) {
                                    sel.value = sel.options[0].value;
                                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                                    filled++;
                                }
                            }
                        }
                    }

                    // Fill text inputs
                    const inputs = applyArea.querySelectorAll(
                        'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"]):not([type="file"]):not([style*="display: none"]), ' +
                        'textarea:not([style*="display: none"])'
                    );
                    for (const inp of inputs) {
                        if (inp.offsetParent === null) continue;
                        const val = (inp.value || '').trim();
                        if (val === '' || val === 'Select' || val === '--Select--') {
                            const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
                            const ariaLabel = (inp.getAttribute('aria-label') || '').toLowerCase();
                            const ctx = (inp.parentElement ? inp.parentElement.innerText || '' : '').toLowerCase();

                            let fillVal = '';
                            if (ph.includes('ctc') || ph.includes('salary') || ctx.includes('ctc') || ctx.includes('salary')) {
                                fillVal = defaultCtc;
                            } else if (ph.includes('experience') || ph.includes('year') || ctx.includes('experience') || ctx.includes('year')) {
                                fillVal = defaultExp;
                            } else if (ph.includes('notice') || ctx.includes('notice')) {
                                fillVal = defaultNotice;
                            } else if (ph.includes('location') || ph.includes('city') || ctx.includes('location') || ctx.includes('city')) {
                                fillVal = defaultLocation;
                            } else if (ph.includes('phone') || ph.includes('mobile') || ctx.includes('phone') || ctx.includes('mobile')) {
                                fillVal = '9999999999';
                            } else if (ph.includes('name') || ctx.includes('name')) {
                                fillVal = 'Candidate';
                            } else if (ph.includes('email') || ctx.includes('email')) {
                                fillVal = 'candidate@example.com';
                            } else {
                                fillVal = '1';
                            }

                            const nativeSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            ).set;
                            inp.focus();
                            nativeSetter.call(inp, '');
                            nativeSetter.call(inp, fillVal);
                            inp.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.blur();
                            inp.dispatchEvent(new Event('blur', { bubbles: true }));
                            filled++;
                        }
                    }

                    // Check visible radio/checkbox in apply area
                    const choices = applyArea.querySelectorAll(
                        'input[type="radio"]:not([style*="display: none"]), ' +
                        'input[type="checkbox"]:not([style*="display: none"])'
                    );
                    for (const ch of choices) {
                        if (ch.offsetParent === null) continue;
                        if (!ch.checked) {
                            // Check if it's a "consent/agree" type
                            const lbl = ch.closest('label') || (ch.id && document.querySelector('label[for="' + CSS.escape(ch.id) + '"]'));
                            const ctxText = lbl ? (lbl.innerText || '').toLowerCase() : '';
                            if (ctxText.includes('agree') || ctxText.includes('consent') || ctxText.includes('accept') || ctxText.includes('yes') || ctxText.includes('notify') || ctxText.includes('callback')) {
                                ch.click();
                                ch.checked = true;
                                ch.dispatchEvent(new Event('change', { bubbles: true }));
                                filled++;
                            }
                        }
                    }

                    return filled > 0;
                }""",
                {
                    "defaultCtc": default_ctc,
                    "defaultExp": default_exp,
                    "defaultNotice": default_notice,
                    "defaultLocation": default_location,
                }
            )
            if result:
                logger.info(f"JS force fill completed for remaining required questions")
            return result
        except Exception as e:
            logger.debug(f"JS force fill all failed: {e}")
            return False

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
