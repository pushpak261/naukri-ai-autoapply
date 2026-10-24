"""Shared local retrieval and provenance for screening answers on both platforms."""

import dataclasses
import hashlib
import json
from pathlib import Path

from libs.common.offline_screening import general_technical_question, offline_answer
from libs.common.screening_review import ScreeningReviewStore


def profile_context(settings, candidate):
    if dataclasses.is_dataclass(candidate):
        resume = dataclasses.asdict(candidate)
    else:
        resume = vars(candidate) if hasattr(candidate, "__dict__") else {}
    data = {"profile": settings.profile.model_dump(), "resume": resume}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def memory_store(settings):
    root = getattr(settings, "project_root", None)
    return ScreeningReviewStore(root) if isinstance(root, (str, Path)) else None


def local_answer(question, settings, candidate, job):
    question = {
        "type": question.get("input_type") or question.get("field_type", "text"),
        **question,
    }
    store = memory_store(settings)
    context = profile_context(settings, candidate) if store else ""
    answer = store.answer_for(question, job, context) if store else ""
    if answer:
        return answer, "confirmed_answer"
    answer, source = offline_answer(question, settings, candidate, job)
    if store and answer:
        provenance = "technical" if source == "technical_knowledge" else "profile"
        store.observe(question, answer, job, provenance, context)
    return answer, source


def remember_generated(question, answer, settings, candidate, job):
    store = memory_store(settings)
    if store and answer:
        source = "technical" if general_technical_question(question) else "ai_suggestion"
        store.observe(question, answer, job, source, profile_context(settings, candidate))


def filled_answer(field, answer):
    """Only record values actually accepted by a visible employer control."""
    value = str(field.get("value", ""))
    kind = field["type"]
    if kind == "checkbox":
        expected = "Yes" if value == "Yes" else "No"
        return expected if str(answer).casefold() == expected.casefold() else ""
    if kind in ("dropdown", "radio"):
        return (
            str(answer)
            if any(o["text"] == str(answer) and str(o["value"]) == value for o in field["options"])
            else ""
        )
    if kind == "skill_tags":
        return value

    def normalize(text):
        return str(text).replace("\r\n", "\n").strip()

    return value if normalize(value) == normalize(answer) else ""
