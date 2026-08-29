"""
Fake / scam job detection package.

Consolidates all fake job detection logic — scoring engine, exclusion
specifications, and the 5-stage pipeline — into a single reusable location.

Typical usage:
    from src.naukri_agent.fake_job_detection import (
        FakeJobDetectionPipeline,
        compute_scam_score,
        ScamScoreResult,
        ConsultancyScamSpecification,
    )

    pipeline = FakeJobDetectionPipeline(settings.exclusions)
    pipeline.build_exclusion_spec()
    clean, scam = pipeline.early_scam_filter(jobs)
    if pipeline.is_excluded(job):
        ...
"""

from src.naukri_agent.fake_job_detection.rules import (
    ScamScoreResult,
    compute_scam_score,
    SCAM_THRESHOLD,
    MODERATE_THRESHOLD,
    _count_tech_categories,
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

from src.naukri_agent.fake_job_detection.pipeline import FakeJobDetectionPipeline

__all__ = [
    "ScamScoreResult",
    "compute_scam_score",
    "SCAM_THRESHOLD",
    "MODERATE_THRESHOLD",
    "_count_tech_categories",
    "JobSpecification",
    "AndSpecification",
    "OrSpecification",
    "NotSpecification",
    "CompanyExclusionSpecification",
    "TitleExclusionSpecification",
    "DescriptionExclusionSpecification",
    "ConsultancyScamSpecification",
    "AuthenticityExclusionSpecification",
    "FakeJobDetectionPipeline",
]
