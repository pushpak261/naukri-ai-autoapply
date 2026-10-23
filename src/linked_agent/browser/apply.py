"""
LinkedIn job application module.
Handles the Easy Apply flow including multi-step form filling.
"""

from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import urlsplit


from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage
from src.linked_agent.config.constants import ApplicationStatus
from src.linked_agent.config.settings import Settings
from src.linked_agent.bot.interfaces import IQuestionAnswerer
from src.linked_agent.models.entities import Job
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)
LINKEDIN_HOSTS = ("www.linkedin.com", "linkedin.com")


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
        external_applier=None,
    ) -> None:
        self._detail_page = detail_page
        self._settings = settings
        self._question_answerer = question_answerer
        self._external_applier = external_applier

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
        self._submission_attempted = False
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
                            return result

                # No Easy Apply — try clicking ANY Apply button (may open Easy Apply modal or external site)
                # Set up popup listener before clicking
                new_page_url = None
                listener_active = False
                opened_external_pages = []

                async def on_popup(popup, opened_pages=opened_external_pages):
                    nonlocal new_page_url
                    opened_pages.append(popup)
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
                            return await self._apply_external(page, new_page_url, job)

                        current_url = page.url
                        if urlsplit(current_url).hostname not in LINKEDIN_HOSTS:
                            return await self._apply_external(page, current_url, job)

                        # Only close pages that are external (not LinkedIn), not all other pages
                        for p in page.context.pages:
                            if p != page and urlsplit(p.url or "").hostname not in LINKEDIN_HOSTS:
                                try:
                                    ext_url = p.url
                                    await p.close()
                                    if ext_url:
                                        return await self._apply_external(page, ext_url, job)
                                except Exception:
                                    pass

                        # No external nav detected — check for Easy Apply modal with longer timeout
                        modal_appeared = await self._detail_page.wait_for_apply_modal(timeout=8000)
                        if modal_appeared:
                            logger.info(f"Apply button opened modal — treating as Easy Apply: {job.title}")
                            result = await self._handle_easy_apply_flow(job)
                            return result

                        # Double-check for late-opening tabs
                        if new_page_url and new_page_url != page.url:
                            return await self._apply_external(page, new_page_url, job)

                        logger.info(f"Apply button clicked but no result: {job.title}")
                        return {"status": ApplicationStatus.SKIPPED_EASY_APPLY_UNAVAILABLE, "error_message": "No result after click"}

                    logger.info(f"No Apply button found: {job.title} @ {job.company}")
                    return {"status": ApplicationStatus.SKIPPED_EASY_APPLY_UNAVAILABLE, "error_message": "No Apply button found"}

                finally:
                    if listener_active:
                        with contextlib.suppress(Exception):
                            page.context.remove_listener("page", on_popup)
                        listener_active = False
                    for external_page in opened_external_pages:
                        if urlsplit(external_page.url).hostname not in LINKEDIN_HOSTS:
                            with contextlib.suppress(Exception):
                                await external_page.close()

            except Exception as e:
                if self._submission_attempted:
                    return {"status": ApplicationStatus.UNCERTAIN, "error_message": "Connection failed during submission; review before retrying."}
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

    async def _apply_external(self, page, url, job):
        if not self._settings.application.skip_external_apply and self._external_applier:
            return await self._external_applier.apply(page, url, job)
        return {"status": ApplicationStatus.SKIPPED_EXTERNAL, "external_url": url,
                "error_message": "External employer applications are disabled."}

    async def _answer_screening_questions_locally(self, questions: list[dict], job: Job) -> list[dict]:
        from libs.common.screening import evidence_answer
        candidate = getattr(self._question_answerer, '_resume', None)
        return [{'question': q.get('question', ''), 'answer': evidence_answer(q, self._settings, candidate)} for q in questions]

    async def _submit_once_and_confirm(self) -> dict:
        if getattr(self, '_submission_attempted', False):
            return {"status": ApplicationStatus.UNCERTAIN, "error_message": "Submission was already attempted; review before retrying."}
        self._submission_attempted = True
        clicked = await self._detail_page.submit_application()
        if not clicked:
            self._submission_attempted = False
            return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": "Submit is unavailable or disabled. Check required fields."}
        for _ in range(6):
            await asyncio.sleep(1)
            if await self._detail_page.has_submit_success():
                return {"status": ApplicationStatus.APPLIED}
        return {"status": ApplicationStatus.UNCERTAIN, "error_message": "Submission was attempted once but platform confirmation is missing. Review before retrying."}

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

        from pathlib import Path
        resume_path = ''
        if self._settings.resume.path:
            root = Path(self._settings.project_root).resolve()
            selected = (root / self._settings.resume.path).resolve()
            if selected.is_relative_to(root) and selected.is_file():
                resume_path = str(selected)

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
                    with contextlib.suppress(Exception):
                        await page.screenshot(path=f"debug_0questions_{job.linkedin_job_id}.png")

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
                    return await self._submit_once_and_confirm()

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
                        if stuck_count >= 2:
                            logger.error("Form stuck in loop — aborting")
                            break
                    else:
                        stuck_count = 0
            else:
                stuck_count = 0

            logger.info(f"Step {step} questions: {len(questions)} — {[(q.get('question','')[:40], q.get('field_type',''), q.get('current_value','')[:20]) for q in questions]}")

            # Only a resume/CV field may receive the selected resume.
            for fq in (q for q in questions if q.get('field_type') == 'file'):
                if fq.get('current_value'):
                    continue
                label = str(fq.get('question', '')).casefold()
                is_resume = 'resume' in label or 'résumé' in label or 'cv' in label.split()
                if not is_resume:
                    if fq.get('required', fq.get('is_required', True)):
                        return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": "A required non-resume attachment needs review."}
                    continue
                if not resume_path:
                    if fq.get('required', fq.get('is_required', True)):
                        return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": "Select an available resume before applying."}
                    continue
                if not await self._detail_page.upload_resume_file(resume_path, field_id=fq.get('input_id')):
                    return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": "Resume upload failed; submission was blocked."}
                await asyncio.sleep(2)

            # Handle text/dropdown/radio/checkbox questions
            SKIP_PATTERNS = ["deselect resume", "select resume", "follow ", "remove resume"]
            non_file_questions = [
                q for q in questions
                if q.get("field_type") != "file"
                and str(q.get('current_value') or '').strip().casefold() in ('', 'select', 'select an option', '--select--', 'choose')
                and not any(q.get("question", "").lower().startswith(p) for p in SKIP_PATTERNS)
            ]
            if non_file_questions:
                if self._settings.ai.use_gemini:
                    answers = await self._question_answerer.answer_questions(non_file_questions, job)
                else:
                    answers = await self._answer_screening_questions_locally(non_file_questions, job)
                for q, a in zip(non_file_questions, answers, strict=True):
                    answer_text = a.get("answer", "")
                    field_type = q.get("field_type", "text")
                    # For radio buttons, only fill the "Yes" or best answer, skip if answer is empty
                    if field_type == "radio" and not answer_text and not q.get("required", q.get("is_required", True)):
                        logger.debug(f"Step {step}: Skipping radio with no answer: {q.get('question','')[:30]}")
                        continue
                    if not answer_text and q.get('required', q.get('is_required', True)):
                        return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": f"Save a confirmed answer in Preferences before retrying: {q.get('question', 'Unlabelled required question')}"}
                    if answer_text:
                        filled = await self._detail_page.fill_answer(q, answer_text)
                        if not filled and q.get('required', q.get('is_required', True)):
                            return {"status": ApplicationStatus.SKIPPED_SCREENING, "error_message": "Could not fill a required screening field. Review the application form."}
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
                return await self._submit_once_and_confirm()

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
                review_state = {}
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

                return await self._submit_once_and_confirm()

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
                    return {"status": ApplicationStatus.UNCERTAIN, "error_message": "No platform confirmation; review before retrying."}
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
            return {"status": ApplicationStatus.UNCERTAIN, "error_message": "No platform confirmation; review before retrying."}

        await self._detail_page.close_apply_modal()
        return {
            "status": ApplicationStatus.UNCERTAIN,
            "error_message": f"Application flow completed {step} steps without clear result",
        }
