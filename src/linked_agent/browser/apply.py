"""
LinkedIn job application module.
Handles the Easy Apply flow including multi-step form filling.
"""

from __future__ import annotations

import asyncio
import contextlib
import os


from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage
from src.linked_agent.config.constants import ApplicationStatus
from src.linked_agent.config.settings import Settings
from src.linked_agent.bot.interfaces import IQuestionAnswerer
from src.linked_agent.models.entities import Job
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInJobApplier:
    """
    Handles LinkedIn Easy Apply job application flow.

    The Easy Apply process is a multi-step modal:
    1. Click "Easy Apply" button
    2. Fill screening questions (may span multiple steps)
    3. Review and submit
    """

    def __init__(
        self,
        detail_page: LinkedInJobDetailPage,
        settings: Settings,
        question_answerer: IQuestionAnswerer,
    ) -> None:
        self._detail_page = detail_page
        self._settings = settings
        self._question_answerer = question_answerer

    async def apply_to_job(self, job: Job, retries: int | None = None, sidebar_already_applied: bool = False) -> dict[str, str]:
        """
        Attempt to apply to a LinkedIn job via Easy Apply or external link.

        Args:
            job: The job to apply to
            retries: Number of retries (None = use max_retries from settings, 1 = no retries)
            sidebar_already_applied: Pre-checked "already applied" flag

        Returns:
            Dictionary with 'status' and optional 'error_message' and 'external_url'.
        """
        if retries is None:
            retries = self._settings.application.max_retries
        last_error = ""
        page = self._detail_page.page

        for attempt in range(1, retries + 1):
            try:
                # Log current page URL for debugging
                current_url = page.url
                logger.info(f"Apply check — current URL: {current_url}")

                # Brief wait for the Apply button area to render (React lazy loading)
                await asyncio.sleep(2)

                # Check if already applied — use pre-computed value from sidebar if available
                if sidebar_already_applied:
                    logger.info(f"Already applied to: {job.title} @ {job.company}")
                    return {
                        "status": ApplicationStatus.SKIPPED_ALREADY_APPLIED,
                        "error_message": "Already applied",
                    }

                # Check for Easy Apply — trust the pre-extracted flag first, then verify via DOM
                has_ea = job.easy_apply or await self._detail_page.has_easy_apply()

                if has_ea:
                    # Click Easy Apply with one immediate retry if it fails
                    clicked = await self._detail_page.click_easy_apply()
                    if not clicked:
                        await asyncio.sleep(3)
                        clicked = await self._detail_page.click_easy_apply()

                    if not clicked:
                        logger.warning("Easy Apply click failed, falling back to external apply check")
                    elif clicked:
                        # Wait for the modal to appear (click_easy_apply returns
                        # immediately after clicking — modal may take a moment)
                        await asyncio.sleep(3)
                        modal_appeared = await self._detail_page.wait_for_apply_modal()
                        if not modal_appeared:
                            # Modal slow — wait once more
                            await asyncio.sleep(3)
                            modal_appeared = await self._detail_page.wait_for_apply_modal()

                        if not modal_appeared:
                            # Modal failed — capture debug info and fall through
                            try:
                                debug_info = await page.evaluate("""
                                    () => {
                                        return {
                                            url: window.location.href,
                                            title: document.title,
                                            hasDialog: !!document.querySelector('[role="dialog"]'),
                                            hasModal: !!document.querySelector('[class*="modal"]'),
                                            buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                                                text: (b.innerText || '').trim().substring(0, 50),
                                                visible: b.offsetParent !== null,
                                                cls: (b.className || '').substring(0, 50)
                                            })).filter(b => b.visible && b.text)
                                        };
                                    }
                                """)
                                logger.warning(f"Debug info: URL={debug_info.get('url')}, dialog={debug_info.get('hasDialog')}, modal={debug_info.get('hasModal')}, buttons={debug_info.get('buttons', [])[:3]}")
                            except Exception as e:
                                logger.debug(f"Could not capture debug info: {e}")
                            # Fall through to external apply check
                        else:
                            # Handle multi-step application form
                            result = await self._handle_easy_apply_flow(job)
                            if result.get("status") == ApplicationStatus.UNCERTAIN:
                                await self._detail_page.close_apply_modal()
                                await asyncio.sleep(2)
                                # One retry of the entire flow
                                result = await self._handle_easy_apply_flow(job)
                                if result.get("status") != ApplicationStatus.UNCERTAIN:
                                    return result
                            else:
                                return result

                # No Easy Apply — try clicking ANY Apply button (may open Easy Apply modal or external site)
                # Set up popup listener before clicking
                new_page_url = None
                listener_active = False

                async def on_popup(popup):
                    nonlocal new_page_url
                    try:
                        await popup.wait_for_load_state("domcontentloaded", timeout=10000)
                        new_page_url = popup.url
                    except Exception:
                        new_page_url = popup.url if popup.url else None

                try:
                    page.context.on("page", on_popup)
                    listener_active = True

                    clicked_any = await self._detail_page.click_any_apply_button()
                    if clicked_any:
                        await asyncio.sleep(3)

                        # Check for EXTERNAL first (fast path — most "Apply" buttons are external)
                        if new_page_url and new_page_url != page.url:
                            logger.info(f"Apply button opened new tab: {new_page_url[:100]}")
                            return {"status": ApplicationStatus.SKIPPED_EXTERNAL, "external_url": new_page_url}

                        current_url = page.url
                        if "linkedin.com" not in current_url:
                            return {"status": ApplicationStatus.SKIPPED_EXTERNAL, "external_url": current_url}

                        # Only close pages that are external (not LinkedIn), not all other pages
                        for p in page.context.pages:
                            if p != page and "linkedin.com" not in (p.url or ""):
                                try:
                                    ext_url = p.url
                                    await p.close()
                                    if ext_url:
                                        return {"status": ApplicationStatus.SKIPPED_EXTERNAL, "external_url": ext_url}
                                except Exception:
                                    pass

                        # No external nav detected — check for Easy Apply modal with longer timeout
                        modal_appeared = await self._detail_page.wait_for_apply_modal(timeout=8000)
                        if modal_appeared:
                            logger.info(f"Apply button opened modal — treating as Easy Apply: {job.title}")
                            result = await self._handle_easy_apply_flow(job)
                            if result.get("status") != ApplicationStatus.UNCERTAIN:
                                return result
                            logger.info(f"Easy Apply flow UNCERTAIN for {job.title} — external")
                            return {"status": ApplicationStatus.SKIPPED_EXTERNAL, "external_url": current_url}

                        # Double-check for late-opening tabs
                        if new_page_url and new_page_url != page.url:
                            return {"status": ApplicationStatus.SKIPPED_EXTERNAL, "external_url": new_page_url}

                        logger.info(f"Apply button clicked but no result: {job.title}")
                        return {"status": ApplicationStatus.SKIPPED_EASY_APPLY_UNAVAILABLE, "error_message": "No result after click"}

                    logger.info(f"No Apply button found: {job.title} @ {job.company}")
                    return {"status": ApplicationStatus.SKIPPED_EASY_APPLY_UNAVAILABLE, "error_message": "No Apply button found"}

                finally:
                    if listener_active:
                        try:
                            page.context.remove_listener("page", on_popup)
                        except Exception:
                            pass
                        listener_active = False

            except Exception as e:
                last_error = str(e)
                logger.error(f"Apply error (attempt {attempt}/{retries}) for {job.title} @ {job.company}: {e}")
                if attempt < retries:
                    with contextlib.suppress(Exception):
                        await self._detail_page.close_apply_modal()
                    await asyncio.sleep(2)

        return {
            "status": ApplicationStatus.FAILED,
            "error_message": f"Failed after {retries} attempts: {last_error}",
        }

    async def _answer_screening_questions_locally(self, questions: list[dict[str, str]], job: Job) -> list[dict]:
        """Answer screening questions locally without AI when models are exhausted.

        Uses heuristics based on the question text, field type, and available options.
        Handles location/country/city dropdowns by using the user's configured location.
        """
        location = ""
        try:
            location = self._settings.search.preferred_locations[0] if self._settings.search.preferred_locations else "India"
        except Exception:
            location = "India"

        # Pull profile fields from settings
        profile = self._settings.profile if hasattr(self._settings, 'profile') else None
        first_name = (getattr(profile, 'first_name', '') or '').strip()
        last_name = (getattr(profile, 'last_name', '') or '').strip()
        phone = (getattr(profile, 'phone', '') or '').strip()
        profile_email = (getattr(profile, 'email', '') or '').strip()
        current_ctc = (getattr(profile, 'current_ctc', '') or '').strip()
        expected_ctc = (getattr(profile, 'expected_ctc', '') or '').strip()
        notice_period = (getattr(profile, 'notice_period', '') or '').strip()
        total_exp = (getattr(profile, 'total_experience', '') or '').strip()

        import re as _re
        answers = []
        for q in questions:
            question_lower = q.get("question", "").lower()
            field_type = q.get("field_type", "text")
            options = q.get("options", [])
            answer = ""

            # Name fields
            if field_type == "text" and any(kw in question_lower for kw in ["first name", "firstname", "given name"]):
                answer = first_name or "Candidate"
            elif field_type == "text" and any(kw in question_lower for kw in ["last name", "lastname", "family name", "surname"]):
                answer = last_name or "Unknown"
            elif field_type == "text" and any(kw in question_lower for kw in ["phone", "mobile", "telephone", "contact number"]):
                answer = phone or "Not specified"
            elif field_type == "text" and any(kw in question_lower for kw in ["email", "e-mail", "email address"]):
                answer = profile_email or "Not specified"

            # Location/Country/City dropdown — auto-select user's location
            elif field_type == "dropdown" and any(kw in question_lower for kw in ["location", "country", "city", "state", "province"]):
                loc_parts = location.split(",")
                priority = [loc_parts[0].strip(), location.strip(), loc_parts[-1].strip()] if len(loc_parts) > 1 else [location.strip()]
                if location.lower() != "india":
                    priority.append("India")
                for candidate in priority:
                    if candidate in options:
                        answer = candidate
                        break
                if not answer:
                    for opt in options:
                        opt_lower = opt.lower()
                        if any(kw in opt_lower for kw in ["india", "any", "remote", "global", "worldwide"]):
                            answer = opt
                            break
                if not answer:
                    answer = options[0] if options else "India"

            # Yes/No radio — default to "Yes" for positive questions
            elif field_type == "radio" and options:
                if any(kw in question_lower for kw in ["comfortable", "willing", "able", "authorize", "sponsor", "visa", "work permit", "legally", "eligible", "right to work", "commute", "shift", "remote", "work from home", "hybrid", "relocate", "relocation"]):
                    answer = next((opt for opt in options if opt.lower().strip() == "yes"), "")
                    if not answer:
                        answer = next((opt for opt in options if any(p in opt.lower() for p in ("yes", "i am", "willing", "agree", "confirm"))), options[0])
                elif "salary" in question_lower or "compensation" in question_lower or "gender" in question_lower or "ethnicity" in question_lower or "veteran" in question_lower or "disability" in question_lower:
                    pass
                else:
                    positives = [opt for opt in options if opt.lower().strip() in ("yes", "true", "i agree", "confirm", "i accept", "agree")]
                    answer = positives[0] if positives else ("Yes" if any(o.lower().strip() == "yes" for o in options) else options[0])

            # Dropdown with specific patterns
            elif field_type == "dropdown" and options:
                if any(kw in question_lower for kw in ["how many", "years", "experience", "month"]):
                    sorted_opts = sorted(options, key=lambda o: float(_re.sub(r'[^0-9.]', '', o)) if _re.sub(r'[^0-9.]', '', o) else 999)
                    answer = sorted_opts[0] if sorted_opts else ""
                elif any(kw in question_lower for kw in ["education", "degree", "qualification"]):
                    for edu in ["bachelor", "bachelor's", "be", "b.tech", "master", "master's", "m.tech", "phd"]:
                        match = next((opt for opt in options if edu in opt.lower()), None)
                        if match: answer = match; break
                elif any(kw in question_lower for kw in ["language", "english", "proficiency"]):
                    for lang in ["fluent", "native", "professional", "advanced", "intermediate", "basic"]:
                        match = next((opt for opt in options if lang in opt.lower()), None)
                        if match: answer = match; break
                elif any(kw in question_lower for kw in ["current ctc", "salary", "compensation", "annual"]):
                    if current_ctc: answer = current_ctc
                elif any(kw in question_lower for kw in ["expected ctc", "expect"]):
                    if expected_ctc: answer = expected_ctc
                elif any(kw in question_lower for kw in ["notice", "notice period"]):
                    if notice_period: answer = notice_period

            # Text fields for profile data
            elif field_type == "text":
                if any(kw in question_lower for kw in ["location", "city", "current location"]):
                    answer = "Pune Division, Maharashtra, India" if ("pune" in location.lower() or not location) else location
                elif any(kw in question_lower for kw in ["current ctc", "current salary"]):
                    answer = current_ctc
                elif any(kw in question_lower for kw in ["expected ctc", "expected salary"]):
                    answer = expected_ctc
                elif any(kw in question_lower for kw in ["notice", "notice period"]):
                    answer = notice_period
                elif any(kw in question_lower for kw in ["experience", "years of experience", "total exp"]):
                    answer = total_exp

            answers.append({"answer": answer, "question": q.get("question", "")})
        return answers

    async def _handle_easy_apply_flow(self, job: Job) -> dict[str, str]:
        """
        Navigate through the multi-step Easy Apply form.
        LinkedIn forms can have 1-5+ steps including:
        - Contact info
        - Resume selection
        - Screening questions
        - Work authorization
        - Review
        """
        max_steps = 15
        step = 0
        modal_found = False
        last_step_signatures = []
        stuck_count = 0
        page = self._detail_page.page

        # Find resume file path for uploads
        resume_path = ""
        try:
            rp = self._settings.resume.path
            if rp:
                from pathlib import Path
                resume_path = str(Path(self._settings.project_root) / rp)
        except Exception:
            pass
        if not resume_path:
            for candidate in ["resume.pdf", "data/resumes/resume.pdf"]:
                full = os.path.join(str(self._settings.project_root), candidate)
                if os.path.isfile(full):
                    resume_path = full
                    break

        while step < max_steps:
            step += 1
            logger.info(f"Easy Apply step {step} for {job.title}")

            await asyncio.sleep(2)

            if not modal_found:
                modal_found = await self._detail_page.wait_for_apply_modal(timeout=5000)
                if not modal_found:
                    logger.warning("Easy Apply modal not found")
                    break

            # Check for 0-step success (click Easy Apply → success screen immediately)
            if await self._detail_page.has_submit_success():
                logger.info(f"Successfully applied to (0-step): {job.title} @ {job.company}")
                return {"status": ApplicationStatus.APPLIED}

            # Extract questions from current step FIRST
            questions = await self._detail_page.extract_screening_questions()

            # Diagnostic: when 0 questions detected, try advancing immediately
            # LinkedIn pre-fills some applications entirely (contact info, resume)
            if not questions:
                if step == 1:
                    modal_text = await self._detail_page.get_modal_text()
                    logger.warning(f"Step {step}: 0 questions detected — modal text: {modal_text[:300]}")
                    if "NO MODAL FOUND" in modal_text:
                        logger.warning("False-positive modal — bailing out")
                        break
                    try:
                        await page.screenshot(path=f"debug_0questions_{job.linkedin_job_id}.png")
                    except Exception:
                        pass

                # Try Submit/Review/Next immediately when no questions found
                # (pre-filled form or info-only step)
                has_submit = await page.evaluate("""
                () => {
                    const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                    if (!modal) return false;
                    const btns = modal.querySelectorAll('button');
                    for (const b of btns) {
                        const text = (b.innerText || '').trim().toLowerCase();
                        const label = (b.getAttribute('aria-label') || '').toLowerCase();
                        if ((text.includes('submit') || label.includes('submit')) && b.offsetParent !== null && !b.disabled) return true;
                    }
                    return false;
                }
                """)
                if has_submit:
                    logger.info(f"Step {step}: No questions + Submit available — clicking Submit")
                    await self._detail_page.submit_application()
                    await asyncio.sleep(3)
                    if await self._detail_page.has_submit_success():
                        logger.info(f"Successfully applied to: {job.title} @ {job.company}")
                        return {"status": ApplicationStatus.APPLIED}
                    modal_still_open = await self._detail_page.wait_for_apply_modal(timeout=3000)
                    if not modal_still_open:
                        logger.info(f"Application modal closed after submit: {job.title}")
                        return {"status": ApplicationStatus.APPLIED}

            # Build step signature for loop detection
            step_sig = "|".join(f"{q.get('question','')[:30]}:{q.get('field_type','')}" for q in questions)
            if step_sig:
                last_step_signatures.append(step_sig)
                # Check if any signature appears 2+ times in last 4 steps (catches loops early)
                if len(last_step_signatures) >= 2:
                    recent = last_step_signatures[-4:]
                    count = recent.count(step_sig)
                    if count >= 2:
                        stuck_count += 1
                        logger.warning(f"Step {step}: stuck in loop ({stuck_count}x) — signature repeated {count}x in last {len(recent)} steps")
                        # Try Submit instead of Next when stuck
                        has_submit = await page.evaluate("""
                        () => {
                            const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                            if (!modal) return false;
                            const btns = modal.querySelectorAll('button');
                            for (const b of btns) {
                                const text = (b.innerText || '').trim().toLowerCase();
                                const label = (b.getAttribute('aria-label') || '').toLowerCase();
                                if ((text.includes('submit') || label.includes('submit')) && b.offsetParent !== null && !b.disabled) return true;
                            }
                            return false;
                        }
                        """)
                        if has_submit:
                            logger.info(f"Step {step}: Trying Submit to break loop")
                            await self._detail_page.submit_application()
                            await asyncio.sleep(3)
                            if await self._detail_page.has_submit_success():
                                logger.info(f"Successfully applied to: {job.title} @ {job.company}")
                                return {"status": ApplicationStatus.APPLIED}
                            modal_still_open = await self._detail_page.wait_for_apply_modal(timeout=3000)
                            if not modal_still_open:
                                logger.info(f"Application modal closed after loop-submit: {job.title}")
                                return {"status": ApplicationStatus.APPLIED}
                        if stuck_count >= 2:
                            logger.error("Form stuck in loop — aborting")
                            break
                    else:
                        stuck_count = 0
            else:
                stuck_count = 0

            logger.info(f"Step {step} questions: {len(questions)} — {[(q.get('question','')[:40], q.get('field_type',''), q.get('current_value','')[:20]) for q in questions]}")

            # Handle file upload questions
            file_uploads = [q for q in questions if q.get("field_type") == "file"]
            if file_uploads:
                for fq in file_uploads:
                    if fq.get("current_value"):
                        logger.info(f"Step {step}: File already uploaded: {fq['current_value']}")
                    elif resume_path:
                        uploaded = await self._detail_page.upload_resume_file(resume_path)
                        logger.info(f"Step {step}: Resume upload attempt: {uploaded}")
                        await asyncio.sleep(2)
                    else:
                        logger.warning(f"Step {step}: No resume file configured — skipping upload")

            # Handle text/dropdown/radio/checkbox questions
            SKIP_PATTERNS = ["deselect resume", "select resume", "follow ", "remove resume"]
            non_file_questions = [
                q for q in questions
                if q.get("field_type") != "file"
                and not any(q.get("question", "").lower().startswith(p) for p in SKIP_PATTERNS)
            ]
            if non_file_questions:
                if self._settings.ai.enable_matching:
                    answers = await self._question_answerer.answer_questions(non_file_questions, job)
                else:
                    answers = await self._answer_screening_questions_locally(non_file_questions, job)
                for q, a in zip(non_file_questions, answers):
                    answer_text = a.get("answer", "")
                    field_type = q.get("field_type", "text")
                    # For radio buttons, only fill the "Yes" or best answer, skip if answer is empty
                    if field_type == "radio" and not answer_text:
                        logger.debug(f"Step {step}: Skipping radio with no answer: {q.get('question','')[:30]}")
                        continue
                    if answer_text:
                        filled = await self._detail_page.fill_answer(q, answer_text)
                        logger.info(f"Step {step} fill '{q.get('question','')[:30]}' = '{answer_text[:30]}': {filled}")
                        await asyncio.sleep(0.5)
                    else:
                        logger.warning(f"Step {step} empty answer for '{q.get('question','')[:30]}' — skipping")

            # Unfollow company if configured
            if self._settings.application.unfollow_after_apply:
                await self._detail_page.unfollow_company()

            # Track validation error back-navigation to prevent infinite loops
            if 'validation_back_count' not in locals():
                validation_back_count = 0

            # AFTER filling questions, check for Review/Submit (end of form)
            has_submit = await page.evaluate("""
            () => {
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const btns = modal.querySelectorAll('button');
                for (const b of btns) {
                    const text = (b.innerText || '').trim().toLowerCase();
                    const label = (b.getAttribute('aria-label') || '').toLowerCase();
                    if ((text.includes('submit') || label.includes('submit')) && b.offsetParent !== null && !b.disabled) return true;
                }
                return false;
            }
            """)
            if has_submit:
                logger.info(f"Step {step}: Submit button found — clicking")
                await self._detail_page.submit_application()
                await asyncio.sleep(3)
                if await self._detail_page.has_submit_success():
                    logger.info(f"Successfully applied to: {job.title} @ {job.company}")
                    return {"status": ApplicationStatus.APPLIED}
                modal_still_open = await self._detail_page.wait_for_apply_modal(timeout=3000)
                if not modal_still_open:
                    logger.info(f"Application modal closed (likely success): {job.title}")
                    return {"status": ApplicationStatus.APPLIED}
                # Log modal content after failed submit for debugging
                modal_text = await self._detail_page.get_modal_text()
                logger.info(f"Step {step}: Modal after submit: {modal_text[:200]}")

            has_review = await page.evaluate("""
            () => {
                const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                if (!modal) return false;
                const btns = modal.querySelectorAll('button');
                for (const b of btns) {
                    const text = (b.innerText || '').trim().toLowerCase();
                    const label = (b.getAttribute('aria-label') || '').toLowerCase();
                    if ((text.includes('review') || label.includes('review')) && b.offsetParent !== null && !b.disabled) return true;
                }
                return false;
            }
            """)
            if has_review:
                logger.info(f"Step {step}: Review button found — clicking")
                await self._detail_page.click_review()
                # Wait for review page to fully load
                await asyncio.sleep(3)

                # Dump modal state after Review for debugging
                try:
                    review_state = await page.evaluate("""() => {
                        const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                        if (!modal) return {found: false};
                        const btns = [];
                        modal.querySelectorAll('button').forEach(b => {
                            if (b.offsetParent !== null) {
                                btns.push({
                                    text: (b.innerText || '').trim().substring(0, 60),
                                    ariaLabel: b.getAttribute('aria-label') || '',
                                    disabled: b.disabled
                                });
                            }
                        });
                        return {found: true, buttons: btns, text: (modal.innerText || '').substring(0, 300)};
                    }""")
                    logger.info(f"Step {step}: Post-Review modal state: {review_state}")
                except Exception as e:
                    logger.debug(f"Could not dump review state: {e}")

                # Check if validation failed (Review button still present = went back to questions)
                still_has_review = any(
                    'review' in (b.get('text', '') + b.get('ariaLabel', '')).lower()
                    for b in (review_state.get('buttons', []) if isinstance(review_state, dict) else [])
                )
                if still_has_review:
                    # Check for validation errors in modal text
                    modal_text = review_state.get('text', '') if isinstance(review_state, dict) else ''
                    has_validation_error = 'please enter' in modal_text.lower() or 'required' in modal_text.lower() or 'make a selection' in modal_text.lower()
                    if has_validation_error:
                        validation_back_count += 1
                        if validation_back_count >= 3:
                            logger.warning(f"Step {step}: Validation back-navigation loop detected ({validation_back_count}x) — aborting")
                            break
                        logger.warning(f"Step {step}: Review has validation errors — going Back to fix (attempt {validation_back_count}/3)")
                        # Click Back to return to form
                        await page.evaluate("""
                        () => {
                            const modal = document.querySelector('div[role="dialog"], .jobs-easy-apply-modal');
                            if (!modal) return;
                            const btns = modal.querySelectorAll('button');
                            for (const b of btns) {
                                const text = (b.innerText || '').trim().toLowerCase();
                                const label = (b.getAttribute('aria-label') || '').toLowerCase();
                                if ((text === 'back' || label.includes('back')) && b.offsetParent !== null) {
                                    b.click();
                                    return;
                                }
                            }
                        }
                        """)
                        await asyncio.sleep(2)
                        # The loop will re-extract and re-fill on next iteration
                        continue
                    else:
                        logger.warning(f"Step {step}: Review button still present — validation may have failed, skipping job")
                        break

                # On the review page, look for Submit button with retries
                for submit_attempt in range(3):
                    submitted = await self._detail_page.submit_application()
                    if submitted:
                        logger.info(f"Step {step}: Submit clicked on review page (attempt {submit_attempt+1})")
                        await asyncio.sleep(3)
                        if await self._detail_page.has_submit_success():
                            logger.info(f"Successfully applied to: {job.title} @ {job.company}")
                            return {"status": ApplicationStatus.APPLIED}
                        modal_still_open = await self._detail_page.wait_for_apply_modal(timeout=3000)
                        if not modal_still_open:
                            logger.info(f"Application modal closed after submit: {job.title}")
                            return {"status": ApplicationStatus.APPLIED}
                        modal_text = await self._detail_page.get_modal_text()
                        logger.info(f"Step {step}: Modal after review submit ({submit_attempt+1}): {modal_text[:200]}")
                    # Maybe the review page has additional questions — try Next
                    clicked_next = await self._detail_page.click_next()
                    if clicked_next:
                        logger.info(f"Step {step}: Clicked Next on review page (attempt {submit_attempt+1})")
                        await asyncio.sleep(2)
                        break
                    break

                # Final check: maybe it was submitted and modal is closing
                await asyncio.sleep(2)
                if await self._detail_page.has_submit_success():
                    return {"status": ApplicationStatus.APPLIED}
                modal_still_open = await self._detail_page.wait_for_apply_modal(timeout=3000)
                if not modal_still_open:
                    logger.info(f"Application modal closed (likely success): {job.title}")
                    return {"status": ApplicationStatus.APPLIED}

            # Try Next/Continue
            clicked_next = await self._detail_page.click_next()
            logger.info(f"Step {step}: Next button clicked: {clicked_next}")
            if not clicked_next:
                # No Next button — check if modal closed (success) or truly stuck
                await asyncio.sleep(1)
                if await self._detail_page.has_submit_success():
                    logger.info(f"Successfully applied to (post-step): {job.title} @ {job.company}")
                    return {"status": ApplicationStatus.APPLIED}
                modal_still = await self._detail_page.wait_for_apply_modal(timeout=3000)
                if not modal_still:
                    logger.info(f"Modal closed without Next/Submit — likely success: {job.title}")
                    return {"status": ApplicationStatus.APPLIED}
                logger.warning(f"No Next button at step {step} — form may be complete or stuck")
                break

            await asyncio.sleep(1)

        # If we exhausted all steps without clear success/failure,
        # do a final modal-closed check before returning UNCERTAIN
        await asyncio.sleep(2)
        if await self._detail_page.has_submit_success():
            logger.info(f"Successfully applied to (final check): {job.title} @ {job.company}")
            return {"status": ApplicationStatus.APPLIED}
        modal_open = await self._detail_page.wait_for_apply_modal(timeout=3000)
        if not modal_open:
            logger.info(f"Modal gone after exhausting steps — treating as success: {job.title}")
            return {"status": ApplicationStatus.APPLIED}

        await self._detail_page.close_apply_modal()
        return {
            "status": ApplicationStatus.UNCERTAIN,
            "error_message": f"Application flow completed {step} steps without clear result",
        }
