"""Pydantic schemas for run management endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RunCreate(BaseModel):
    dry_run: bool = False
    cap: int | None = None
    threshold: int | None = Field(default=None, ge=0, le=100)


class RunStatus(BaseModel):
    run_id: int | None = None
    status: str = "idle"
    phase: str = ""
    dry_run: bool = False
    jobs_found: int = 0
    jobs_applied: int = 0
    jobs_skipped: int = 0
    jobs_failed: int = 0
    daily_cap_remaining: int = 0
    processed_count: int = 0
    total_queued: int = 0
    error: str | None = None


class RunSummary(BaseModel):
    id: int
    started_at: str
    ended_at: str
    keywords: list[str] = Field(default_factory=list)
    found: int = 0
    applied: int = 0
    skipped: int = 0
    failed: int = 0
    status: str = ""

    @field_validator("keywords", mode="before")
    @classmethod
    def _coerce_keywords(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []
