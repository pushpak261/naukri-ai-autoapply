"""
Reusable fake/scam job detection pipeline.

Consolidates all 5 stages of scam/fake job filtering into a single
orchestration class that can be used by any agent (Naukri, LinkedIn, etc.).

=== PIPELINE STAGES ===

Stage 1 — Early Scam Pass
    Scores jobs using only title + company name (description not yet available).
    Uses ConsultancyScamSpecification which catches obvious agency companies,
    phone numbers in title, personal emails in title, hidden company names, etc.
    Returns (clean_jobs, scam_jobs) for separate handling.

Stage 2 — Config Exclusion Specs
    Applies configured blocklists:
      - CompanyExclusionSpecification (exact company name matches)
      - TitleExclusionSpecification (keyword matches in job title)
      - DescriptionExclusionSpecification (keyword matches in description)

Stage 3 — Authenticity Exclusion
    Three checks:
      - Fake company blocklist
      - Hidden/generic company name ("MNC", "Confidential")
      - No company logo + suspiciously high number of openings

Stage 4 — TF-IDF Similarity Filter
    Pre-filter using cosine similarity between resume and job text.
    Jobs below the similarity threshold are skipped before AI matching.

Stage 5 — Deep Scam Re-check
    Runs the full 26+ signal compute_scam_score() with complete job data
    (including full description). Catches WhatsApp numbers, phone spam,
    freshers ads, overseas recruiter patterns, and all other signals.

Usage:
    pipeline = FakeJobDetectionPipeline(settings.exclusions)

    # Stage 1: Early filter on scraped jobs (before AI matching)
    clean_jobs, scam_jobs = pipeline.early_scam_filter(all_jobs)
    for j in scam_jobs:
        log_info(f"Scam removed: {j.title} @ {j.company}")

    # Build exclusion spec (Stages 2+3+5) — called once
    pipeline.build_exclusion_spec()

    # Later, for each job after description fetch:
    if pipeline.is_excluded(job):
        continue  # Stage 5 deep re-check caught it

    # Stage 4: TF-IDF similarity check
    passed, score = pipeline.check_similarity(text, vector_filter)
"""

from __future__ import annotations

from src.naukri_agent.config.settings import ExclusionSettings
from src.naukri_agent.models.entities import Job
from src.naukri_agent.fake_job_detection.rules import (
    AuthenticityExclusionSpecification,
    CompanyExclusionSpecification,
    ConsultancyScamSpecification,
    DescriptionExclusionSpecification,
    EARLY_SCAM_THRESHOLD,
    JobSpecification,
    TitleExclusionSpecification,
    compute_scam_score,
)

MIN_HEURISTIC_THRESHOLD: float = 0.10


class FakeJobDetectionPipeline:
    """
    Encapsulates the full fake/scam job detection pipeline into a single
    reusable component.

    All 5 stages are available as distinct methods so callers can interleave
    them with their own workflow (e.g., fetching descriptions between stages).
    """

    def __init__(self, exclusion_settings: ExclusionSettings) -> None:
        if exclusion_settings is None:
            raise ValueError("exclusion_settings is required")

        self._exclusion_settings = exclusion_settings
        self._exclusion_spec: JobSpecification | None = None
        self._exclusion_spec_no_title: JobSpecification | None = None

    # ------------------------------------------------------------------
    # Stage 1: Early scam pass — lenient (higher threshold, no description)
    #
    # Uses EARLY_SCAM_THRESHOLD (200) instead of SCAM_THRESHOLD (80)
    # because we have only title+company data. Only undeniable scams
    # (agency in company, overseas recruiter, financial terms) get caught.
    # Everything else passes to be re-evaluated with full description data
    # in the deep check (Stage 5).
    # ------------------------------------------------------------------
    def early_scam_filter(self, jobs: list[Job]) -> tuple[list[Job], list[Job]]:
        """
        Stage 1: Run early scam/consultancy detection using only title and
        company name (description may not be available yet).

        Uses a higher threshold (EARLY_SCAM_THRESHOLD = 200) so that
        only undeniable scams/consultancies are removed early. Borderline
        cases pass through to be evaluated with full description data in
        Stage 5 (deep_scam_check).

        Args:
            jobs: List of scraped Job entities (may have partial data).

        Returns:
            Tuple of (clean_jobs, scam_jobs).
            Returns (jobs, []) if scam filter is disabled in settings.
        """
        if not jobs:
            return [], []

        if not self._exclusion_settings.enable_scam_filter:
            return jobs, []

        clean_jobs: list[Job] = []
        scam_jobs: list[Job] = []
        for job in jobs:
            result = compute_scam_score(job)
            if result.raw_score >= EARLY_SCAM_THRESHOLD:
                scam_jobs.append(job)
            else:
                clean_jobs.append(job)
        return clean_jobs, scam_jobs

    # ------------------------------------------------------------------
    # Stages 2 + 3: Config-based exclusion specification composition
    #
    # NOTE: ConsultancyScamSpecification (Stage 5) is NOT included here.
    # It's used separately in deep_scam_check() after description fetch,
    # so that full data (description, logo, salary) is available for
    # accurate scoring.
    # ------------------------------------------------------------------
    def build_exclusion_spec(self) -> JobSpecification:
        """
        Build the composed exclusion specification covering:
          Stage 2 — Company / Title / Description keyword blocklists
          Stage 3 — Authenticity checks (fake company blocklist, hidden names, no-logo + high openings)

        Does NOT include ConsultancyScamSpecification — that's run separately
        in deep_scam_check() after full description data is available.

        Returns the composed JobSpecification so callers can inspect or store it.

        Must be called before is_excluded().
        """
        exclusions = self._exclusion_settings
        common_spec: JobSpecification = (
            CompanyExclusionSpecification(exclusions.companies)
            | DescriptionExclusionSpecification(exclusions.description_keywords)
            | AuthenticityExclusionSpecification(
                exclusions.fake_company_blocklist,
                exclusions.max_openings_without_logo,
            )
        )
        title_spec = TitleExclusionSpecification(exclusions.title_keywords)
        self._exclusion_spec = common_spec | title_spec
        self._exclusion_spec_no_title = common_spec
        return self._exclusion_spec

    def is_excluded(self, job: Job, heuristic_score: float | None = None) -> bool:
        """
        Stages 2, 3: Check a single job against config-based exclusion specs.

        When a heuristic_score is provided and exceeds MIN_HEURISTIC_THRESHOLD,
        the title keyword exclusion is skipped — the job has enough semantic
        similarity to the resume to warrant further evaluation by the AI matcher.
        Only company, description, and authenticity checks remain active.

        Does NOT run ConsultancyScamSpecification — use deep_scam_check()
        for that (requires full description data).

        Must call build_exclusion_spec() first before using this method.

        Args:
            job: The Job entity to evaluate.
            heuristic_score: Optional TF-IDF similarity score (0.0-1.0).
                             If >= MIN_HEURISTIC_THRESHOLD, title keyword
                             exclusion is bypassed.

        Returns:
            True if the job matches any exclusion rule and should be skipped.
        """
        if self._exclusion_spec is None:
            return False
        if heuristic_score is not None and heuristic_score >= MIN_HEURISTIC_THRESHOLD:
            return self._exclusion_spec_no_title.is_satisfied_by(job) if self._exclusion_spec_no_title else False
        return self._exclusion_spec.is_satisfied_by(job)

    # ------------------------------------------------------------------
    # Stage 5: Deep scam re-check (with full description data)
    # ------------------------------------------------------------------
    def deep_scam_check(self, job: Job) -> bool:
        """
        Stage 5: Run full ConsultancyScamSpecification against a job with
        complete data (including description, logo, salary, openings).

        Uses SCAM_THRESHOLD (80) with all 26+ signals active, including
        genuine signals (G2-G4) that offset suspicious patterns. This
        ensures borderline cases that passed the lenient Stage 1 filter
        are accurately evaluated now that description data is available.

        Respects enable_scam_filter setting — returns False (allows job)
        when scam filtering is disabled.

        Args:
            job: The Job entity with full description data.

        Returns:
            True if the job is identified as a scam/consultancy.
        """
        if not self._exclusion_settings.enable_scam_filter:
            return False
        return ConsultancyScamSpecification().is_satisfied_by(job)

    # ------------------------------------------------------------------
    # Stage 4: TF-IDF similarity filter
    # ------------------------------------------------------------------
    @staticmethod
    def check_similarity(
        job_text: str,
        vector_filter,
        threshold: float = 0.10,
    ) -> tuple[bool, float]:
        """
        Stage 4: Pre-filter using TF-IDF cosine similarity with the resume.

        Args:
            job_text: Combined text from job title, company, skills, and description.
            vector_filter: A VectorSimilarityFilter instance built with resume data.
            threshold: Minimum similarity score to pass (default 0.10).

        Returns:
            Tuple of (passed, score) where passed is True if score >= threshold.
        """
        if not job_text or vector_filter is None:
            return False, 0.0
        score = vector_filter.get_similarity_score(job_text)
        return score >= threshold, score

    # ------------------------------------------------------------------
    # Stage 6: Job Deduplication Helper
    # ------------------------------------------------------------------
    @staticmethod
    def deduplicate_jobs(
        jobs: list[Job],
        applied_job_ids: set[str] | None = None,
        applied_composites: set[tuple[str, str]] | None = None,
    ) -> tuple[list[Job], list[Job]]:
        """
        Deduplicates a list of jobs by naukri_job_id and title+company composite.

        Args:
            jobs: Scraped jobs.
            applied_job_ids: Set of job IDs already in database.
            applied_composites: Set of (title_lower, company_lower) pairs already in database.

        Returns:
            Tuple of (unique_jobs, duplicate_jobs)
        """
        if not jobs:
            return [], []

        applied_ids = applied_job_ids or set()
        applied_comps = applied_composites or set()

        seen_ids = set(applied_ids)
        seen_comps = set(applied_comps)

        unique_jobs: list[Job] = []
        duplicate_jobs: list[Job] = []

        for job in jobs:
            j_id = str(job.naukri_job_id or "").strip()
            comp_key = ((job.title or "").strip().lower(), (job.company or "").strip().lower())

            if j_id and j_id in seen_ids or comp_key[0] and comp_key[1] and comp_key in seen_comps:
                duplicate_jobs.append(job)
            else:
                if j_id:
                    seen_ids.add(j_id)
                if comp_key[0] and comp_key[1]:
                    seen_comps.add(comp_key)
                unique_jobs.append(job)

        return unique_jobs, duplicate_jobs

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def is_scam_filter_enabled(self) -> bool:
        """Whether the scam detection filter is enabled in settings."""
        return self._exclusion_settings.enable_scam_filter

    @property
    def exclusion_spec(self) -> JobSpecification | None:
        """The built exclusion specification (None if build_exclusion_spec() not called)."""
        return self._exclusion_spec
