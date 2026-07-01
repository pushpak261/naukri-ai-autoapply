"""
Core domain entities for the Naukri Auto-Apply Agent.
Separates domain logic and type safety from databases and external APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Job:
    """Core domain Entity representing a job listing scraped from Naukri."""

    naukri_job_id: str
    title: str
    company: str
    url: str
    location: str = ""
    experience: str = ""
    salary: str = ""
    description: str = ""
    skills: str = ""  # Comma-separated skill tags
    posted_date: str = ""
    is_verified: bool | None = None
    company_rating: float | None = None
    is_external_apply: bool | None = None
    external_apply_url: str | None = None
    hiring_for: str | None = None
    is_consultant_post: bool | None = None
    scraped_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None

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
