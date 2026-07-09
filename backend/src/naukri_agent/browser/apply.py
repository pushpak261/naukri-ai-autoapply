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

from src.naukri_agent.ai.question_answerer import _normalize_question_text
from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job
from src.naukri_agent.bot.interfaces import IQuestionAnswerer, IRepository
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
        repository: IRepository | None = None,
    ) -> None:
        self._detail_page = detail_page
        self._settings = settings
        self._qa = question_answerer
        self._repo = repository

    async def _record_failed_question(
        self,
        question: dict,
        job: Job,
    ) -> None:
        if not self._repo:
            return
        question_text = (question.get("question") or "").strip()
        if not question_text:
            return
        question_key = _normalize_question_text(question_text)
        await self._repo.upsert_failed_question(
            question_text=question_text,
            question_key=question_key,
            question_type=question.get("type", "text"),
            options=question.get("options"),
            last_job_id=job.id,
        )

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

            # Naukri's apply redirect goes through about:blank before landing on
            # the real myapply URL. If we ended up there, keep waiting until the
            # actual destination loads (up to 10 s).
            page = self._detail_page._engine.page
            if page.url.startswith("about:"):
                for _ in range(20):
                    await asyncio.sleep(0.5)
                    if not page.url.startswith("about:"):
                        break
                if not page.url.startswith("about:"):
                    try:
                        await self._detail_page._interactions.wait_for_navigation_complete(
                            timeout=8000
                        )
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
        # Wait for apply modal/flow to render (Naukri loads questions asynchronously)
        await self._detail_page.wait_for_apply_ui(timeout=8000)
        await asyncio.sleep(1)

        # If the page is still at about:blank at this point the navigation did
        # not complete correctly. Abort early to avoid burning the full 300 s
        # job timeout on LLM retries against an empty page.
        page = self._detail_page._engine.page
        if page.url.startswith("about:"):
            log_warning(
                f"Page stuck at about:blank after Apply click for '{job.title}' — "
                "navigation did not complete. Marking as failed."
            )
            return {
                "status": ApplicationStatus.FAILED,
                "error_message": "Page remained at about:blank after Apply click; navigation incomplete",
            }

        # Check for early failure indicators
        failure_msg = await self._detail_page.check_application_failure()
        if failure_msg:
            if self._is_unanswered_questions_failure(failure_msg):
                log_info("Mandatory questions detected early — filling with AI...")
                answered = await self._fill_screening_questions(job)
                if answered:
                    await self._detail_page.submit_application()
                    await asyncio.sleep(2)
                    if await self._detail_page.check_application_success():
                        log_success(f"Applied successfully (after early screening fill): {job.title}")
                        return {"status": ApplicationStatus.APPLIED, "error_message": ""}
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
            if not self._is_unanswered_questions_failure(failure_msg):
                log_error(f"Application failed: {failure_msg}")
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": f"Application rejected: {failure_msg}",
                }

        # Check for immediate success
        if await self._detail_page.check_application_success():
            log_success(f"Applied successfully (direct): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

        # Check for screening questions or visible apply form
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

            # Check for failure indicators — retry once on mandatory questions
            failure_msg = await self._detail_page.check_application_failure()
            if failure_msg and self._is_unanswered_questions_failure(failure_msg):
                log_info("Mandatory questions still unanswered — retrying screening fill...")
                await asyncio.sleep(1)
                if await self._fill_screening_questions(job):
                    await self._detail_page.submit_application()
                    await asyncio.sleep(2)
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

        if await self._detail_page.is_already_applied():
            log_success(f"Application confirmed (already applied indicator): {job.title}")
            return {"status": ApplicationStatus.APPLIED, "error_message": ""}

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

        profile = getattr(self._qa, "_profile", None)
        name = (profile.name if profile and profile.name else "Candidate")
        email = (profile.email if profile and profile.email else "")
        phone = (profile.phone if profile and profile.phone else "")
        location = (
            self._settings.profile.current_location
            or (profile.current_title if profile else None)
            or "Pune"
        )
        notice = self._settings.profile.notice_period or "Immediate"
        current_ctc = self._settings.profile.current_ctc or "4.5 LPA"
        expected_ctc = self._settings.profile.expected_ctc or "6 LPA"
        total_exp = (
            self._settings.profile.total_experience
            or (f"{profile.total_experience_years} years" if profile and profile.total_experience_years else "1")
        )
        skills_summary = ", ".join((profile.skills[:8] if profile and profile.skills else ["Java", "React", "Spring Boot"]))

        # Helper to pick closest choice
        def pick_option(keywords, default):
            for kw in keywords:
                for opt in options:
                    if kw in opt.lower():
                        return opt
            return options[0] if options else default

        if q_type in ("radio", "dropdown", "checkbox"):
            if "reloc" in q_text or "travel" in q_text or "shift" in q_text or "agree" in q_text or "willing" in q_text:
                return pick_option(["yes", "agree", "true", "willing", "y"], "Yes")
            if "notice" in q_text:
                return pick_option(["immediate", "0 days", "15 days", "serving", "no notice"], notice)
            if "gender" in q_text:
                return pick_option(["male", "female", "prefer not"], options[0] if options else "Male")
            if "experience" in q_text or "years" in q_text:
                return pick_option(["1", "2", "0-1", "1-2", "3"], options[0] if options else str(int(profile.total_experience_years) if profile and profile.total_experience_years else 1))
            if "ctc" in q_text or "salary" in q_text or "package" in q_text:
                if "expected" in q_text or "desired" in q_text:
                    return pick_option(["6", "5", "7"], options[0] if options else expected_ctc)
                return pick_option(["4", "5", "4.5"], options[0] if options else current_ctc)
            if "location" in q_text or "city" in q_text or "based" in q_text:
                return pick_option([location.lower(), "pune", "mumbai", "bangalore"], location)
            if "skill" in q_text or "technology" in q_text or "proficien" in q_text:
                return pick_option(["yes", "expert", "proficient", "intermediate"], "Yes")
            return options[0] if options else "Yes"
        else:
            # Text / number / date fields
            if "experience" in q_text or "years" in q_text or "month" in q_text:
                nums = re.findall(r"\d+(?:\.\d+)?", str(total_exp))
                return nums[0] if nums else "1"
            if "ctc" in q_text or "salary" in q_text or "package" in q_text:
                ctc_val = expected_ctc if ("expected" in q_text or "desired" in q_text) else current_ctc
                nums = re.findall(r"\d+(?:\.\d+)?", ctc_val)
                if "rupee" in q_text or "rs" in q_text or "annual" in q_text or "lpa" not in q_text.lower():
                    if nums:
                        return str(int(float(nums[0]) * 100000))
                return nums[0] if nums else "6"
            if "notice" in q_text:
                return notice
            if "location" in q_text or "city" in q_text:
                return location
            if "phone" in q_text or "mobile" in q_text:
                return phone or "9999999999"
            if "email" in q_text:
                return email or "candidate@email.com"
            if "name" in q_text:
                return name
            if "why" in q_text or "join" in q_text or "fit" in q_text or "motivat" in q_text:
                return (
                    f"I am a {profile.current_title if profile and profile.current_title else 'Full Stack Developer'} "
                    f"with experience in {skills_summary}. I am excited about this role and confident I can contribute "
                    f"from day one with strong problem-solving skills and a collaborative mindset."
                )
            if "project" in q_text or "describe" in q_text or "achievement" in q_text:
                if profile and profile.work_experience:
                    first = profile.work_experience[0]
                    title = first.get("title", "Software Engineer")
                    company = first.get("company", "my previous company")
                    return f"In my role as {title} at {company}, I built scalable full-stack applications using modern technologies and delivered measurable business impact."
                return "I have built production-grade full-stack applications using Java, Spring Boot, React, and cloud technologies."
            if "relocate" in q_text or "travel" in q_text or "shift" in q_text:
                return "Yes"
            return "Yes"

    async def _fill_question(self, question: dict, answer: str, job: Job) -> bool:
        answer = (answer or "").strip()
        if not answer:
            answer = self._generate_safe_fallback_for_question(question)
        if not answer:
            await self._record_failed_question(question, job)
            return False

        success = await self._detail_page.fill_question_answer(question, answer)
        if success:
            return True

        await self._record_failed_question(question, job)
        return False

    async def _fill_screening_questions(self, job: Job) -> bool:
        """
        Extract, answer, and fill screening questions iteratively.
        Handles dynamic follow-up questions and validates mandatory fields.
        Optimized to avoid wasting AI tokens on questions that resolve
        deterministically or don't change between iterations.
        """
        try:
            max_attempts = 5
            attempt = 0
            seen_questions: set[str] = set()
            last_unfilled_count = 0
            stale_iterations = 0

            while attempt < max_attempts:
                attempt += 1
                logger.info(f"Screening questions fill attempt {attempt}/{max_attempts}...")

                # Extract questions
                questions = await self._detail_page.extract_screening_questions()
                if not questions:
                    if await self._detail_page._is_apply_modal_visible() or await self._detail_page.is_chatbot_flow():
                        logger.debug("Apply modal visible but no questions parsed yet — waiting...")
                        await asyncio.sleep(1.5)
                        continue
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
                            await self._fill_question(q, fallback, job)
                            await self._detail_page.action_delay()
                    break

                # Skip questions we've already tried (waste of AI tokens)
                fresh_questions = [
                    q
                    for q in unfilled_questions
                    if q.get("id") or q.get("question", "") not in seen_questions
                ]
                if not fresh_questions:
                    logger.info(
                        "All unfilled questions previously attempted. Using safe fallbacks."
                    )
                    for q in unfilled_questions:
                        fallback = self._generate_safe_fallback_for_question(q)
                        if fallback:
                            await self._fill_question(q, fallback, job)
                            await self._detail_page.action_delay()
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
                    confidence = str(ans.get("confidence", "")).lower()

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
                        await self._record_failed_question(matching_q, job)
                        a_val = self._generate_safe_fallback_for_question(matching_q)
                        logger.info(f"Using safe fallback '{a_val}' for: '{q_text}'")
                    elif confidence == "low":
                        await self._record_failed_question(matching_q, job)

                    if a_val:
                        success = await self._fill_question(matching_q, a_val, job)
                        if success:
                            filled_any = True
                            await self._detail_page.action_delay()

                # For chatbot flows, we submit immediately after filling to show next question
                if filled_any and await self._detail_page.is_chatbot_flow():
                    await self._detail_page.submit_application()
                elif not filled_any:
                    log_warning(
                        "Could not fill screening questions via AI — trying safe fallbacks"
                    )
                    for q in unfilled_questions:
                        fallback = self._generate_safe_fallback_for_question(q)
                        if fallback and await self._fill_question(q, fallback, job):
                            filled_any = True
                            await self._detail_page.action_delay()
                    if not filled_any:
                        break

                await asyncio.sleep(2)

            # Final validation check (use safe fallbacks for any remaining required questions)
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
                    await self._fill_question(q, fallback, job)
                    await self._detail_page.action_delay()

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
                    logger.error(
                        f"Validation FAILED: Required questions still empty: "
                        f"{[q.get('question') for q in still_empty]}"
                    )
                    for q in still_empty:
                        await self._record_failed_question(q, job)
                    return False

            return True

        except Exception as e:
            logger.error(f"Failed in screening questions loop: {e}")
            return False
