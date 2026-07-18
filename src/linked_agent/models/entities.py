"""
Core domain entities for the LinkedIn Auto-Apply Agent.
Separates domain logic and type safety from databases and external APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Job:
    """Core domain Entity representing a job listing scraped from LinkedIn."""

    linkedin_job_id: str
    title: str
    company: str
    url: str
    location: str = ""
    experience: str = ""
    salary: str = ""
    description: str = ""
    skills: str = ""  # Comma-separated skill tags
    posted_date: str = ""
    job_type: str = ""  # full_time, part_time, contract, internship
    work_type: str = ""  # on_site, remote, hybrid
    applicant_count: int = 0
    openings: int = 0
    has_company_logo: bool = False
    easy_apply: bool = False
    easy_apply_url: str = ""  # Direct Easy Apply URL
    company_logo_url: str = ""
    scraped_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None
    card_index: int = -1  # Index of the job card on the search results page (-1 = unknown)
    search_url: str = ""  # The search page URL where this job was found (for sidebar navigation)

    def get_skills_list(self) -> list[str]:
        """Helper to get skills as a list."""
        if not self.skills:
            return []
        return [s.strip() for s in self.skills.split(",") if s.strip()]


@dataclass
class JobApplication:
    """Core domain Entity representing a job application attempt."""

    job_id: int | None = None
    match_score: float = 0.0
    status: str = ""
    match_reasoning: str = ""
    matching_skills: str = ""  # Comma-separated
    missing_skills: str = ""  # Comma-separated
    error_message: str = ""
    should_apply: bool = False
    applied_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None

    def get_matching_skills_list(self) -> list[str]:
        if not self.matching_skills:
            return []
        return [s.strip() for s in self.matching_skills.split(",") if s.strip()]

    def get_missing_skills_list(self) -> list[str]:
        if not self.missing_skills:
            return []
        return [s.strip() for s in self.missing_skills.split(",") if s.strip()]


@dataclass
class ResumeProfile:
    """Core domain Entity representing a parsed candidate resume profile."""

    name: str = ""
    email: str = ""
    phone: str = ""
    current_title: str = ""
    summary: str = ""
    total_experience_years: float = 0.0
    skills: list[str] = field(default_factory=list)
    technical_skills: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    job_titles_held: list[str] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    work_experience: list[dict[str, Any]] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    key_achievements: list[str] = field(default_factory=list)
    file_hash: str = ""
    raw_text: str = ""
