"""Pydantic schemas for job and application endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobCard(BaseModel):
    id: int | None = None
    naukri_job_id: str
    title: str
    company: str
    location: str = ""
    experience: str = ""
    salary: str = ""
    url: str = ""
    posted_date: str = ""
    skills: str = ""
    status: str | None = None
    match_score: float | None = None
    match_reasoning: str | None = None
    applied_at: str | None = None


class JobListResponse(BaseModel):
    items: list[JobCard]
    total: int
    offset: int
    limit: int


class ApplicationRecord(BaseModel):
    job_title: str
    company: str
    location: str = ""
    match_score: float = 0.0
    status: str = ""
    applied_at: str = ""
    url: str = ""
    error_message: str = ""


class ConfigSummary(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    experience_min: int = 0
    experience_max: int = 0
    daily_cap: int = 0
    match_score_threshold: int = 0
    dry_run: bool = False
    require_verified_job: bool = False
    min_company_rating: float = 0.0
    big_companies: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    excluded_title_keywords: list[str] = Field(default_factory=list)
    ai_model: str = ""
