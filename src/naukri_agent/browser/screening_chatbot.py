"""Advance native screening one observed question at a time."""

import asyncio

from playwright.async_api import Error as PlaywrightError

from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)

CHATBOT_CONTAINERS = (
    '.chatbot_Drawer, [class*="chatbot-container" i], [class*="chat-panel" i], '
    '[class*="nI-chatbot"], [class*="chatbot_" i], [class*="screening-bot"], '
    '[class*="screening_bot"], [class*="apply-chat"]'
)


def question_identity(questions):
    """Values/ordinal field IDs can change without advancing the question."""
    return tuple(
        (
            q.get("question", ""),
            q.get("type", ""),
            tuple(
                str(o.get("text", o)) if isinstance(o, dict) else str(o)
                for o in q.get("options", [])
            ),
        )
        for q in questions
    )


def unanswered(question):
    raw = question.get("value")
    value = str(raw if raw is not None else "").strip()
    return not value or value.casefold() in ("select", "--select--", "choose")


async def _wait_for_advance(detail, previous):
    for _ in range(20):
        if await detail.check_application_success():
            return "submitted"
        if await detail.check_application_failure():
            return "validation"
        current = await detail.extract_screening_questions()
        if current and question_identity(current) != previous:
            return "advanced"
        if not current and not await detail.is_chatbot_flow():
            return "receipt_pending"
        await asyncio.sleep(0.5)
    return "stalled"


def _answer_for(question, answers):
    return next(
        (
            answer
            for answer in answers
            if answer.get("question") == question.get("question")
            and (not answer.get("id") or answer.get("id") == question.get("id"))
        ),
        None,
    )


def _trusted(answer):
    return bool(
        answer
        and str(answer.get("answer", "")).strip()
        and answer.get("confidence") not in ("low", "unknown", "needs_input")
    )


async def _fill_missing(worker, job, questions):
    missing = [q for q in questions if unanswered(q)]
    if not missing:
        return True
    answers = await worker._qa.answer_questions(missing, job)
    pairs = [(q, _answer_for(q, answers)) for q in missing]
    worker.unanswered_questions = [
        q.get("question", "Unreadable question") for q, answer in pairs if not _trusted(answer)
    ]
    if worker.unanswered_questions:
        return False
    before = question_identity(questions)
    for question, answer in pairs:
        if not await worker._detail_page.fill_answer_by_metadata(question, str(answer["answer"])):
            worker.unanswered_questions = [question.get("question", "Unreadable question")]
            return False
        # An option can advance automatically. Its old field IDs must not be
        # used to fill or Save the next question.
        current = await worker._detail_page.extract_screening_questions()
        if question_identity(current) != before:
            break
    return True


async def _save_step(worker, previous, questions):
    worker.unanswered_questions = [
        q.get("question", "Unreadable question") for q in questions if unanswered(q)
    ]
    if worker.unanswered_questions:
        return "blocked"
    try:
        clicked = await worker._detail_page.click_chatbot_save_button()
    except PlaywrightError:
        worker._chatbot_submission_uncertain = True
        worker.unanswered_questions = [
            "The chatbot action lost its connection; its result needs verification"
        ]
        return "stalled"
    if not clicked:
        worker.unanswered_questions = ["The chatbot Save control is unavailable or disabled"]
        return "blocked"
    outcome = await _wait_for_advance(worker._detail_page, previous)
    if outcome in ("validation", "stalled"):
        worker._chatbot_submission_uncertain = outcome == "stalled"
        worker.unanswered_questions = [
            "The chatbot did not advance after Save; review its validation message"
        ]
    return outcome


async def _chatbot_step(worker, job):
    detail = worker._detail_page
    if await detail.check_application_success():
        return "submitted"
    questions = await detail.extract_screening_questions()
    if not questions:
        if not await detail.is_chatbot_flow():
            return "receipt_pending"
        worker.unanswered_questions = ["The active chatbot question could not be read"]
        return "blocked"
    before = question_identity(questions)
    if not await _fill_missing(worker, job, questions):
        return "blocked"
    if await detail.check_application_success():
        return "submitted"
    current = await detail.extract_screening_questions()
    if question_identity(current) != before:
        return "advanced"
    return await _save_step(worker, before, current)


async def fill_chatbot(worker, job):
    """Fill/validate, then Save once; never blindly advance the next question."""
    for step in range(32):
        logger.info("Screening chatbot step %s", step + 1)
        outcome = await _chatbot_step(worker, job)
        if outcome in ("submitted", "receipt_pending"):
            return True
        if outcome != "advanced":
            return False
    worker.unanswered_questions = ["The chatbot exceeded 32 screening steps without a receipt"]
    return False
