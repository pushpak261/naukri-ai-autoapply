"""Shared fakes and builders for the question answerer test suite.

Everything here is deterministic and offline: the LLM provider is an
``AsyncMock`` double, the settings/profile/job objects are real domain models
backed by ``tmp_path``, and no browser, network or filesystem writes escape the
per-test temporary directory.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.naukri_agent.ai.question_answerer import QuestionAnswerer
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile

__all__ = [
    "ai_reply",
    "make_answerer",
    "make_job",
    "make_llm",
    "make_profile",
    "make_settings",
    "q",
    "today_ddmmyyyy",
]

_DEFAULT_PROFILE: dict[str, Any] = {
    "current_ctc": "10 LPA",
    "expected_ctc": "15 LPA",
    "notice_period": "30 days",
    "total_experience": "3 years",
    "current_location": "Bangalore",
    "preferred_locations": ["Bangalore", "Pune"],
    "languages": ["English", "Hindi"],
    "github_url": "https://github.com/tester",
    "linkedin_url": "https://linkedin.com/in/tester",
    "date_of_birth": "01/01/1998",
    "marital_status": "Single",
    "reason_for_change": "Looking for a product company",
}


def make_settings(tmp_path: Path, **profile_overrides: Any) -> Settings:
    """Build a real :class:`Settings` rooted at ``tmp_path``."""
    profile_values = dict(_DEFAULT_PROFILE)
    profile_values.update(profile_overrides)
    settings = Settings(project_root=Path(tmp_path))
    for key, value in profile_values.items():
        setattr(settings.profile, key, value)
    return settings


def make_profile(**overrides: Any) -> ResumeProfile:
    """Build a resume profile; ``skills`` defaults to a list of 30+ entries."""
    values: dict[str, Any] = {
        "name": "Jane Developer",
        "email": "jane@example.com",
        "phone": "9998887776",
        "current_title": "Software Engineer",
        "total_experience_years": 3.0,
        "skills": [f"Skill{index}" for index in range(35)],
        "education": [],
        "work_experience": [],
        "key_achievements": [],
        "certifications": [],
        "raw_text": "",
    }
    values.update(overrides)
    return ResumeProfile(**values)


def make_job(**overrides: Any) -> Job:
    """Build a job domain entity."""
    values: dict[str, Any] = {
        "naukri_job_id": "job_1",
        "title": "Java Developer",
        "company": "Acme Corp",
        "url": "https://www.naukri.com/job-details-1",
        "description": "Build Spring Boot services.",
    }
    values.update(overrides)
    return Job(**values)


def make_llm(*replies: str | BaseException) -> MagicMock:
    """Build an LLM provider double returning ``replies`` in order.

    Exception instances (or classes) are raised instead of returned, and a
    ``ValueError`` is raised when more calls happen than replies were scripted.
    """
    llm = MagicMock(name="llm_provider")
    queue = list(replies)

    async def _generate_content(**kwargs: Any) -> str:
        if not queue:
            raise AssertionError("generate_content called more times than scripted")
        reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, type) and issubclass(reply, BaseException):
            raise reply("scripted failure")
        return reply

    llm.generate_content = AsyncMock(side_effect=_generate_content)
    return llm


def make_answerer(
    tmp_path: Path,
    *,
    settings: Settings | None = None,
    profile: ResumeProfile | None = None,
    llm: MagicMock | None = None,
    **profile_overrides: Any,
) -> QuestionAnswerer:
    """Wire a :class:`QuestionAnswerer` with doubles rooted at ``tmp_path``."""
    return QuestionAnswerer(
        llm if llm is not None else make_llm(),
        settings if settings is not None else make_settings(tmp_path, **profile_overrides),
        profile if profile is not None else make_profile(),
    )


def ai_reply(*items: dict) -> str:
    """Serialise AI answer items the way the LLM prompt demands."""
    return json.dumps(list(items))


def q(
    question: str,
    *,
    id: str | None = None,
    type: str = "text",
    options: list[dict] | None = None,
    index: int = 0,
) -> dict:
    """Build a single screening question dict."""
    payload: dict[str, Any] = {"question": question, "type": type, "index": index}
    if id is not None:
        payload["id"] = id
    if options is not None:
        payload["options"] = options
    return payload


def today_ddmmyyyy() -> str:
    """Today's date in the DD/MM/YYYY format used by date answers."""
    return date.today().strftime("%d/%m/%Y")
