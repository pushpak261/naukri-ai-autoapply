"""Backward-compatible re-exports after package layout refactor."""

from src.naukri_agent.models.entities import Job, JobApplication, ResumeProfile

__all__ = ["Job", "JobApplication", "ResumeProfile"]
