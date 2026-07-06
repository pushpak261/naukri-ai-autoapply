"""Backward-compatible re-exports after package layout refactor."""

from src.naukri_agent.models.rules import (
    AndSpecification,
    AuthenticityExclusionSpecification,
    CompanyExclusionSpecification,
    ConsultancyScamSpecification,
    DescriptionExclusionSpecification,
    JobSpecification,
    NotSpecification,
    OrSpecification,
    TitleExclusionSpecification,
)

__all__ = [
    "AndSpecification",
    "AuthenticityExclusionSpecification",
    "CompanyExclusionSpecification",
    "ConsultancyScamSpecification",
    "DescriptionExclusionSpecification",
    "JobSpecification",
    "NotSpecification",
    "OrSpecification",
    "TitleExclusionSpecification",
]
