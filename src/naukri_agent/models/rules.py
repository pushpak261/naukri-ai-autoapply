"""
Specification Pattern implementation for Job matching and exclusion filters.
Allows composing complex rules via logical operators (AND, OR, NOT).

NOTE: This module has been moved to src.naukri_agent.fake_job_detection.rules.
This file is kept as a backward-compatible re-export.
"""

from src.naukri_agent.fake_job_detection.rules import (  # noqa: F401
    ScamScoreResult,
    compute_scam_score,
    JobSpecification,
    AndSpecification,
    OrSpecification,
    NotSpecification,
    CompanyExclusionSpecification,
    TitleExclusionSpecification,
    DescriptionExclusionSpecification,
    ConsultancyScamSpecification,
    AuthenticityExclusionSpecification,
)
