"""
Core abstractions and interfaces for the Naukri Agent.
Using Protocols to enforce dependency inversion and decoupling.
"""

from __future__ import annotations

from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Database Interfaces
# ---------------------------------------------------------------------------
class IRepository(Protocol):
    """Interface for all database operations."""

    async def initialize(self) -> None: ...

    async def save_job(
        self,
        naukri_job_id: str,
        title: str,
        company: str,
        url: str,
        location: str = "",
        experience: str = "",
        salary: str = "",
        description: str = "",
        skills: str = "",
        posted_date: str = "",
    ) -> Any: ...

    def is_already_applied(self, naukri_job_id: str) -> bool: ...

    async def save_application(
        self,
        job_id: int,
        match_score: float,
        status: str,
        match_reasoning: str = "",
        matching_skills: str = "",
        missing_skills: str = "",
        error_message: str = "",
    ) -> Any: ...

    async def get_today_application_count(self) -> int: ...

    async def get_application_stats(self, days: int = 7) -> dict[str, int]: ...

    async def get_recent_applications(self, limit: int = 20) -> list[dict]: ...

    async def save_resume_profile(
        self, file_hash: str, file_path: str, parsed_json: str
    ) -> Any: ...

    async def get_cached_profile(self, file_hash: str) -> dict | None: ...

    async def create_run_log(self, search_keywords: list[str]) -> int: ...

    async def update_run_log(
        self,
        run_log_id: int,
        jobs_found: int = 0,
        jobs_applied: int = 0,
        jobs_skipped: int = 0,
        jobs_failed: int = 0,
        status: str = "completed",
        error_message: str = "",
    ) -> None: ...

    async def get_run_stats(self, limit: int = 10) -> list[dict]: ...


# ---------------------------------------------------------------------------
# LLM Interfaces
# ---------------------------------------------------------------------------
class ILLMProvider(Protocol):
    """Interface for generating text using an LLM."""

    async def generate_content(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_output_tokens: int = 2048,
        response_mime_type: str = "text/plain",
        response_schema: Any = None,
    ) -> str:
        """
        Generate content from a prompt.
        Should return the raw text response.
        """
        ...


# ---------------------------------------------------------------------------
# Browser Interfaces
# ---------------------------------------------------------------------------
class IBrowserEngine(Protocol):
    """Interface for core browser lifecycle management."""

    @property
    def page(self) -> Any: ...

    @property
    def context(self) -> Any: ...

    async def launch(self) -> Any: ...

    async def save_session(self) -> None: ...

    async def close(self) -> None: ...

    def is_alive(self) -> bool: ...


class IBrowserInteractions(Protocol):
    """Interface for high-level human-like browser interactions."""

    async def human_type(self, selector: str, text: str, clear_first: bool = True) -> None: ...

    async def safe_click(self, selector: str, timeout: int = 3000, force: bool = False) -> bool: ...

    async def random_scroll(self, scroll_count: int = 3) -> None: ...

    async def close_popups(self) -> None: ...

    async def wait_for_navigation_complete(self, timeout: int = 30000) -> None: ...

    async def action_delay(self) -> None: ...

    async def get_text_content(self, selector: str) -> str: ...

    async def element_exists(self, selector: str) -> bool: ...


# ---------------------------------------------------------------------------
# AI Component Interfaces
# ---------------------------------------------------------------------------
class IJobFilter(Protocol):
    """Interface for pre-filtering jobs based on heuristic rules or math."""

    def get_similarity_score(self, job_text: str) -> float: ...


class IJobMatcher(Protocol):
    """Interface for scoring a job against a resume."""

    async def match(self, resume_profile: dict, job_data: dict) -> dict: ...


class IQuestionAnswerer(Protocol):
    """Interface for answering application screening questions."""

    async def answer_questions(
        self, questions: list[dict[str, str]], job_data: dict
    ) -> list[dict]: ...


class IResumeParser(Protocol):
    """Interface for parsing a resume PDF."""

    async def parse(self, pdf_path: str) -> dict: ...
