"""
Integration test that simulates the full 5-stage fake job detection pipeline
for both Naukri and LinkedIn agents.

This mirrors what the real agent.run() / _process_jobs() flow does:
  Stage 1 — Early scam pass (title + company only, no description)
  Stage 2 — Exclusion specs (company / title / description keyword blocklists)
  Stage 3 — Authenticity checks (fake company blocklist, hidden name, no-logo + high openings)
  Stage 4 — TF-IDF similarity filter (requires vector filter mock)
  Stage 5 — Deep scam re-check (full description, all 26+ signals)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.naukri_agent.fake_job_detection import (
    FakeJobDetectionPipeline,
    compute_scam_score,
    ScamScoreResult,
    ConsultancyScamSpecification,
    CompanyExclusionSpecification,
    TitleExclusionSpecification,
    DescriptionExclusionSpecification,
    AuthenticityExclusionSpecification,
)
from src.naukri_agent.config.settings import ExclusionSettings


# ---------------------------------------------------------------------------
# Mock VectorSimilarityFilter for Stage 4 testing
# ---------------------------------------------------------------------------
@dataclass
class MockVectorFilter:
    """Returns a configurable similarity score — no real TF-IDF needed."""

    score: float = 0.25

    def get_similarity_score(self, text: str) -> float:
        return self.score


# ---------------------------------------------------------------------------
# Fake ExclusionSettings for testing
# ---------------------------------------------------------------------------
def make_exclusion_settings(**overrides: Any) -> ExclusionSettings:
    defaults: dict[str, Any] = {
        "companies": [
            "Techno Experts",
            "TeleInfoTech",
            "Codinglimits",
        ],
        "title_keywords": [
            "customer support",
            "data entry",
            "sales",
            "bpo",
        ],
        "description_keywords": [
            "send your resume",
            "whatsapp your resume",
            "registration fee",
        ],
        "fake_company_blocklist": [
            "GIST Management Solutions",
            "TheGermanyGuide",
        ],
        "enable_scam_filter": True,
        "max_openings_without_logo": 25,
    }
    defaults.update(overrides)
    return ExclusionSettings(**defaults)



# ---------------------------------------------------------------------------
# Helper: simulate the Naukri agent's full pipeline flow
# ---------------------------------------------------------------------------
def run_naukri_pipeline(
    job,
    exclusion_settings: ExclusionSettings | None = None,
    enable_scam_filter: bool = True,
    mock_score: float = 0.25,
    skip_early: bool = False,
) -> dict[str, Any]:
    """Simulate the Naukri agent's complete flow for a single job.

    Returns a dict with stage results for inspection.
    """
    if exclusion_settings is None:
        exclusion_settings = make_exclusion_settings(
            enable_scam_filter=enable_scam_filter
        )

    pipeline = FakeJobDetectionPipeline(exclusion_settings)
    vector_filter = MockVectorFilter(score=mock_score)

    result: dict[str, Any] = {
        "job": job,
        "stage1_early_scam": None,
        "stage2_exclusion": None,
        "stage3_authenticity": None,
        "stage4_similarity": None,
        "stage5_deep_scam": None,
        "excluded_at": None,
    }

    # ---- Stage 1: Early scam pass (title + company only) ----
    if skip_early:
        result["stage1_early_scam"] = False
    else:
        clean_jobs, scam_jobs = pipeline.early_scam_filter([job])
        is_scam_early = job in scam_jobs
        result["stage1_early_scam"] = is_scam_early
        if is_scam_early:
            result["excluded_at"] = "stage1"
            return result

    # ---- Stage 2+3: Build and check exclusion spec ----
    pipeline.build_exclusion_spec()
    is_excluded_no_desc = pipeline.is_excluded(job, heuristic_score=mock_score)
    result["stage2_exclusion"] = is_excluded_no_desc
    if is_excluded_no_desc:
        result["excluded_at"] = "stage2_before_fetch"
        return result

    # ---- Simulate description fetch (populate the job) ----
    # (job already populated by the caller)

    # ---- Re-check exclusion specs with full description data ----
    is_excluded_full = pipeline.is_excluded(job, heuristic_score=mock_score)
    result["stage3_authenticity"] = is_excluded_full
    if is_excluded_full:
        result["excluded_at"] = "stage3_after_fetch"
        return result

    # ---- Stage 5: Deep scam re-check with full description ----
    is_deep_scam = pipeline.deep_scam_check(job)
    result["stage5_deep_scam"] = is_deep_scam
    if is_deep_scam:
        result["excluded_at"] = "stage5_deep_scam"
        return result

    # ---- Stage 4: TF-IDF similarity (cosmetic ordering vs agent.py) ----
    full_text = f"{job.title} {job.company} {job.skills} {job.description}"
    sim_passed, sim_score = FakeJobDetectionPipeline.check_similarity(
        full_text, vector_filter
    )
    result["stage4_similarity"] = sim_passed
    if not sim_passed:
        result["excluded_at"] = "stage4_similarity"

    return result


# ===========================================================================
# SCENARIO 1: Genuine Software Engineer job
# ===========================================================================
class TestGenuineSoftwareEngineer:
    """A legitimate software engineer job posting should pass ALL stages."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        kwargs = dict(
            naukri_job_id="1",
            title="Software Engineer",
            company="Tech Corp India",
            url="https://naukri.com/job/1",
            description=(
                "We are looking for a Software Engineer with 2+ years of experience "
                "in Python, JavaScript, and React. You will be working on our core "
                "product. Apply through our careers page at careers.techcorp.com."
            ),
            skills="Python, JavaScript, React, Django",
            openings=5,
            has_company_logo=True,
        )
        kwargs.update(overrides)
        return Job(**kwargs)

    def test_passes_all_stages(self):
        job = self.make_job()
        result = run_naukri_pipeline(job)
        assert result["stage1_early_scam"] is False, "Genuine job flagged as scam in stage 1"
        assert result["stage2_exclusion"] is False, "Genuine job matched exclusion spec"
        assert result["stage3_authenticity"] is False, "Genuine job failed authenticity"
        assert result["stage5_deep_scam"] is False, "Genuine job flagged as deep scam"
        assert result["stage4_similarity"] is True, "Genuine job failed similarity"
        assert result["excluded_at"] is None, f"Genuine job excluded at {result['excluded_at']}"


# ===========================================================================
# SCENARIO 2: WhatsApp scam with phone number
# ===========================================================================
class TestWhatsAppScam:
    """Should be caught by Stage 5 deep scam check."""

    _DEFAULT_DESCRIPTION = (
        "Immediate hiring for data entry work from home. Earn Rs 50,000 monthly. "
        "Contact HR on WhatsApp +91 9876543210. Registration fee of Rs 500 required. "
        "Send your resume on WhatsApp."
    )

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        kwargs = dict(
            naukri_job_id="2",
            title="Data Entry Operator",
            company="Quick Earning Solutions",
            url="https://naukri.com/job/2",
            description=self._DEFAULT_DESCRIPTION,
            skills="",
            openings=50,
            has_company_logo=False,
        )
        kwargs.update(overrides)
        return Job(**kwargs)

    def test_caught_by_detection_system(self):
        """Simulate the real agent flow: start with no description, fetch it, then deep-check."""
        settings = make_exclusion_settings()
        pipeline = FakeJobDetectionPipeline(settings)

        # Stage 1: job starts with no description
        job_no_desc = self.make_job(description="")
        clean, scam = pipeline.early_scam_filter([job_no_desc])
        assert job_no_desc not in scam, (
            "Stage 1 caught it even without description"
        )

        # Build exclusion spec for stages 2+3
        pipeline.build_exclusion_spec()

        # Simulate description fetch — create job with full data
        job_full = self.make_job()

        # Stage 5: deep scam check MUST catch it with full description
        assert pipeline.deep_scam_check(job_full), (
            "Deep scam check did not flag the WhatsApp scam"
        )

    def test_already_caught_by_early_scam_if_company_is_blocklisted(self):
        """If company name is on the blocklist, early scam should catch it."""
        job = self.make_job(company="GIST Management Solutions")
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] in ("stage1", "stage2_before_fetch", "stage3_after_fetch")


# ===========================================================================
# SCENARIO 3: Recruitment agency
# ===========================================================================
class TestRecruitmentAgency:
    """Should be caught by Stage 5 deep scam check or Stage 1 if obvious."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="3",
            title="Software Developer",
            company="XYZ Recruitment Pvt Ltd",
            url="https://naukri.com/job/3",
            description=(
                "We are a leading recruitment and staffing company. We have urgent "
                "openings for multiple clients. This is a work from home opportunity. "
                "Call our HR at 9876543210 for more details."
            ),
            skills="Java, Spring",
            openings=10,
            has_company_logo=False,
            **overrides,
        )

    def test_caught_by_detection(self):
        """Agency with obvious recruitment patterns must be caught at some stage."""
        job = self.make_job()
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] is not None, "Agency job not caught by any stage"
        # Verify deep_scam_check would catch it if earlier stages passed
        pipeline = FakeJobDetectionPipeline(make_exclusion_settings())
        assert pipeline.deep_scam_check(job), "Deep scam check did not flag agency job"


# ===========================================================================
# SCENARIO 4: C# Developer (genuine)
# ===========================================================================
class TestCSharpDeveloper:
    """C# in description should trigger G3 tech-category signal, not S9 short-description penalty."""

    _LONG_DESC = (
        "We are looking for a talented C# and ASP.NET Developer to join our product team. "
        "You will design, develop, and maintain our core SaaS platform using C#, ASP.NET Core, "
        "and SQL Server. The ideal candidate has strong experience with RESTful APIs, Entity "
        "Framework, and cloud services like Azure. You will work closely with our frontend "
        "team using React and TypeScript. We follow agile methodologies and practice continuous "
        "integration and deployment. Our tech stack includes C#, ASP.NET, SQL Server, Redis, "
        "Docker, and Azure. We offer competitive salary, flexible work hours, and great "
        "learning opportunities. If you are passionate about building high-quality software "
        "solutions and want to work with a collaborative team, apply now. Must have 2+ years "
        "of experience in C# development."
    )

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="4",
            title="C# Developer",
            company="Product Company",
            url="https://naukri.com/job/4",
            description=self._LONG_DESC,
            skills="C#, .NET, SQL, ASP.NET, React, TypeScript, Azure, Docker",
            openings=3,
            has_company_logo=True,
            **overrides,
        )

    def test_not_flagged_as_scam(self):
        job = self.make_job()
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] is None, (
            f"C# developer wrongly excluded at {result['excluded_at']}"
        )
        # Also verify S9 doesn't fire (short desc has C#)
        score = compute_scam_score(job)
        has_s9 = any("No tech skills" in r for r in score.reasons)
        assert not has_s9, "S9 fired for C# short description (false positive)"
        has_g3 = any("tech categories" in r.lower() for r in score.reasons)
        assert has_g3, "G3 should fire for C# tech category"


# ===========================================================================
# SCENARIO 5: Freshers ad without genuine signals
# ===========================================================================
class TestFreshersAdScam:
    """Freshers ad with WhatsApp number should be caught."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="5",
            title="Fresher Required",
            company="Some Consultancy",
            url="https://naukri.com/job/5",
            description=(
                "Fresher BE/BTech required for top MNC. Immediate joining. "
                "WhatsApp your resume at +91 9876543210."
            ),
            skills="",
            openings=30,
            has_company_logo=False,
            **overrides,
        )

    def test_caught_by_detection(self):
        """Fresher scam with WhatsApp + resume request must be caught at some stage."""
        job = self.make_job()
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] is not None, "Fresher scam not caught by any stage"
        pipeline = FakeJobDetectionPipeline(make_exclusion_settings())
        assert pipeline.deep_scam_check(job), "Deep scam check did not flag fresher scam"


# ===========================================================================
# SCENARIO 6: Multiple cities hiring
# ===========================================================================
class TestMultipleCitiesHiring:
    """S7 should fire for multi-city listings."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="6",
            title="Accountant",
            company="FinanceCorp",
            url="https://naukri.com/job/6",
            description="Hiring for Bangalore and Pune locations.",
            skills="",
            openings=5,
            has_company_logo=True,
            **overrides,
        )

    def test_s7_fires_for_and_separator(self):
        job = self.make_job()
        score = compute_scam_score(job)
        has_s7 = any("Multiple city" in r for r in score.reasons)
        assert has_s7, "S7 should fire for 'Bangalore and Pune'"


# ===========================================================================
# SCENARIO 7: Social media in description
# ===========================================================================
class TestSocialMediaMention:
    """S25 should fire but email @domain should NOT trigger it."""

    def test_s25_fires_for_t_me(self):
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="7a",
            title="Developer",
            company="Some Corp",
            url="",
            description="Join our Telegram group at t.me/jobchannel",
        )
        score = compute_scam_score(job)
        has_s25 = any("Social media handle" in r for r in score.reasons)
        assert has_s25, "S25 should fire for t.me/jobchannel"

    def test_s25_does_not_fire_for_email_domain(self):
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="7b",
            title="Developer",
            company="Some Corp",
            url="",
            description="Please email your resume to hr@gmail.com",
        )
        score = compute_scam_score(job)
        has_s25 = any("Social media handle" in r for r in score.reasons)
        assert not has_s25, "S25 should NOT fire for email domain (@gmail.com)"

    def test_s25_fires_for_instagram_at_handle(self):
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="7c",
            title="Developer",
            company="Some Corp",
            url="",
            description="Contact us on Instagram @company",
        )
        score = compute_scam_score(job)
        has_s25 = any("Social media handle" in r for r in score.reasons)
        assert has_s25, "S25 should fire for Instagram @company"


# ===========================================================================
# SCENARIO 8: Company exclusion spec
# ===========================================================================
class TestCompanyExclusion:
    """Jobs from excluded companies should be caught in Stage 2."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="8",
            title="Software Engineer",
            company="Techno Experts",
            url="https://naukri.com/job/8",
            description="Great job opportunity.",
            skills="Python",
            openings=2,
            has_company_logo=True,
            **overrides,
        )

    def test_excluded_by_company(self):
        job = self.make_job()
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] in ("stage2_before_fetch", "stage3_after_fetch")


# ===========================================================================
# SCENARIO 9: Title keyword exclusion
# ===========================================================================
class TestTitleExclusion:
    """Jobs with excluded title keywords should be caught."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="9",
            title="Customer Support Executive",
            company="Good Company",
            url="https://naukri.com/job/9",
            description="Handle customer queries.",
            skills="",
            openings=2,
            has_company_logo=True,
            **overrides,
        )

    def test_excluded_by_title(self):
        """Title keyword exclusion fires when heuristic score is low."""
        job = self.make_job()
        result = run_naukri_pipeline(job, mock_score=0.0)
        assert result["excluded_at"] in ("stage2_before_fetch", "stage3_after_fetch"), (
            f"Title exclusion should fire, got {result['excluded_at']}"
        )

    def test_title_gating_passes_with_high_heuristic(self):
        """Title exclusion should be bypassed when heuristic score >= 0.20."""
        job = self.make_job()
        result = run_naukri_pipeline(job, mock_score=0.25)
        # With high heuristic score, title gating is bypassed but deep_scam might catch it
        # (SCAM_THRESHOLD=80, and this job scores 160 from BPO+short desc)
        assert result["excluded_at"] == "stage5_deep_scam", (
            f"With high heuristic, should bypass title and reach deep_scam, "
            f"got {result['excluded_at']}"
        )


# ===========================================================================
# SCENARIO 10: Dynamic title gating with high heuristic score
# ===========================================================================
class TestDynamicTitleGating:
    """Title exclusion should be bypassed when heuristic_score >= MIN_HEURISTIC_THRESHOLD."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="10",
            title="Sales Engineer",  # 'sales' is in title_keywords
            company="Tech Corp",
            url="https://naukri.com/job/10",
            description=(
                "Sales engineer role for our SaaS product. Python, JavaScript, and "
                "API integration skills required."
            ),
            skills="Python, JavaScript, APIs",
            openings=3,
            has_company_logo=True,
            **overrides,
        )

    def test_passes_with_high_similarity(self):
        """If heuristic score is high enough, title gating is bypassed."""
        job = self.make_job()
        result = run_naukri_pipeline(job, mock_score=0.25)  # >= 0.20 threshold
        assert result["excluded_at"] is None, (
            f"Sales Engineer with high similarity wrongly excluded at {result['excluded_at']}"
        )

    def test_excluded_with_low_similarity(self):
        """If heuristic score is too low, title exclusion fires."""
        job = self.make_job()
        result = run_naukri_pipeline(job, mock_score=0.0)
        assert result["excluded_at"] in ("stage2_before_fetch", "stage3_after_fetch")


# ===========================================================================
# SCENARIO 11: DescriptionExclusionSpecification with populated description
# ===========================================================================
class TestDescriptionExclusionWithFullData:
    """Description keyword exclusion should fire after description fetch."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        return Job(
            naukri_job_id="11",
            title="Developer",
            company="Unknown Corp",
            url="",
            description=(
                "This is a job posting. Please send your resume to our email."
            ),
            **overrides,
        )

    def test_excluded_by_description_keyword(self):
        """When description is already populated, exclusion fires at first check."""
        job = self.make_job()
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] in ("stage2_before_fetch", "stage3_after_fetch"), (
            f"Should be excluded by description keyword, got {result['excluded_at']}"
        )


# ===========================================================================
# SCENARIO 12: Authenticity check 3 (no logo + high openings)
# ===========================================================================
class TestAuthenticityNoLogoHighOpenings:
    """Jobs without logo and with high openings should be caught."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        kwargs = dict(
            naukri_job_id="12",
            title="Software Developer",
            company="Shady Corp",
            url="",
            description="Great opportunity for developers. Multiple positions available.",
            openings=30,  # > 25 threshold
            has_company_logo=False,
        )
        kwargs.update(overrides)
        return Job(**kwargs)

    def test_excluded_by_authenticity(self):
        job = self.make_job()
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] in ("stage2_before_fetch", "stage3_after_fetch"), (
            f"No-logo high-openings job not caught (got {result['excluded_at']})"
        )

    def test_passes_with_logo(self):
        """Same job with logo should pass."""
        job = self.make_job(has_company_logo=True)
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] is None, (
            f"Job with logo wrongly excluded at {result['excluded_at']}"
        )


# ===========================================================================
# SCENARIO 13: Empty description
# ===========================================================================
class TestEmptyDescription:
    """Jobs with empty description should not crash any stage."""

    def make_job(self, **overrides: Any) -> Any:
        from src.naukri_agent.models.entities import Job

        kwargs = dict(
            naukri_job_id="13",
            title="Python Developer",
            company="InnovateTech Solutions",
            url="",
            description="",
        )
        kwargs.update(overrides)
        return Job(**kwargs)

    def test_no_crash_and_passes_early_stages(self):
        job = self.make_job()
        result = run_naukri_pipeline(job)
        # Should not crash. Stage 5 (deep_scam) may or may not fire,
        # but stages 1-3 should not crash.
        assert result["stage1_early_scam"] is False
        assert result["excluded_at"] is None or result["excluded_at"] == "stage4_similarity"


# ===========================================================================
# SCENARIO 14: Deep scam filter disabled
# ===========================================================================
class TestScamFilterDisabled:
    """When enable_scam_filter is False, only stages 1 and 5 are affected.
    Exclusion specs (stages 2-3: company, title, description keywords) always apply."""

    def test_stage1_and_5_skipped_when_disabled(self):
        """Stage 1 (early) and 5 (deep) should not fire when filter is disabled."""
        exclusion_settings = make_exclusion_settings(enable_scam_filter=False)
        pipeline = FakeJobDetectionPipeline(exclusion_settings)

        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="14",
            title="Data Entry",
            company="Recruitment Pvt Ltd",
            url="",
            description="WhatsApp us. Registration fee required.",
            skills="",
            openings=30,
            has_company_logo=False,
        )
        # Stage 1 returns all jobs as clean
        clean, scam = pipeline.early_scam_filter([job])
        assert job not in scam, "early_scam_filter should not flag when disabled"

        # Stage 5 returns False
        assert not pipeline.deep_scam_check(job), "deep_scam_check should return False when disabled"

    def test_exclusion_specs_still_apply_when_disabled(self):
        """Even when scam filter is disabled, exclusion specs (stages 2-3) still run."""
        exclusion_settings = make_exclusion_settings(enable_scam_filter=False)
        pipeline = FakeJobDetectionPipeline(exclusion_settings)
        pipeline.build_exclusion_spec()

        from src.naukri_agent.models.entities import Job

        # Job with description keyword match
        job = Job(
            naukri_job_id="14b",
            title="Developer",
            company="Some Corp",
            url="",
            description="Please send your resume to us.",
        )
        assert pipeline.is_excluded(job, heuristic_score=0.0), (
            "Description keyword exclusion should still fire when scam filter disabled"
        )

        # Job with company blocklist match
        job2 = Job(
            naukri_job_id="14c",
            title="Developer",
            company="Techno Experts",
            url="",
            description="",
        )
        assert pipeline.is_excluded(job2, heuristic_score=0.0), (
            "Company exclusion should still fire when scam filter disabled"
        )


# ===========================================================================
# SCENARIO 15: Stage 1 early scam with obvious agency company
# ===========================================================================
class TestEarlyScamCatch:
    """Obvious agency/overseas patterns should be caught in Stage 1."""

    def test_overseas_recruiter_in_company(self):
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="15a",
            title="Software Engineer",
            company="Germany Jobs Consultant",
            url="",
            description="",
        )
        result = run_naukri_pipeline(job)
        assert result["excluded_at"] == "stage1", (
            f"Overseas recruiter should be caught in stage 1 (got {result['excluded_at']})"
        )

    def test_phone_number_in_title(self):
        """Phone in title scores 100 — below Stage 1 threshold (200) but above Stage 5 (80)."""
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="15b",
            title="Call 9876543210 for interview",
            company="Some Corp",
            url="",
            description="",
        )
        result = run_naukri_pipeline(job)
        # Stage 1 uses higher threshold (200), phone alone doesn't reach it
        # Stage 5 catches it with SCAM_THRESHOLD=80
        assert result["excluded_at"] in ("stage1", "stage5_deep_scam"), (
            f"Phone in title should be caught, got {result['excluded_at']}"
        )
        if result["excluded_at"] == "stage5_deep_scam":
            pass  # Expected — single phone is 100 < 200 but >= 80


# ===========================================================================
# SCENARIO 16: LinkedIn agent pipeline (LinkedInScamSpecification)
# ===========================================================================
class TestLinkedInScamPipeline:
    """Test the LinkedIn agent's detection with LinkedInScamSpecification."""

    def make_job(self, **overrides: Any) -> Any:
        from src.linked_agent.models.entities import Job as LinkedInJob

        kwargs = dict(
            linkedin_job_id="16",
            title="Software Engineer",
            company="Tech Corp",
            url="https://linkedin.com/jobs/view/16",
            description="",
        )
        kwargs.update(overrides)
        return LinkedInJob(**kwargs)

    def _build_linkedin_exclusion_spec(self, exclusion_settings):
        """Mirror what LinkedIn agent does at lines 273-287."""
        from src.linked_agent.models.rules import (
            CompanyExclusionSpecification as LinkedinCompanyExclusion,
            TitleExclusionSpecification as LinkedinTitleExclusion,
            DescriptionExclusionSpecification as LinkedinDescExclusion,
            AuthenticityExclusionSpecification as LinkedinAuthExclusion,
            LinkedInScamSpecification,
        )

        base = (
            LinkedinCompanyExclusion(exclusion_settings.companies)
            | LinkedinTitleExclusion(exclusion_settings.title_keywords)
            | LinkedinDescExclusion(exclusion_settings.description_keywords)
            | LinkedinAuthExclusion(
                exclusion_settings.fake_company_blocklist,
                exclusion_settings.max_openings_without_logo,
            )
        )

        if exclusion_settings.enable_scam_filter:
            return base | LinkedInScamSpecification()
        return base

    def test_genuine_linkedin_passes(self):
        """A genuine LinkedIn job should pass."""
        job = self.make_job(
            description="Software engineer role with Python, Java, and cloud technologies."
        )
        settings = make_exclusion_settings()
        spec = self._build_linkedin_exclusion_spec(settings)
        assert not spec.is_satisfied_by(job), "Genuine LinkedIn job wrongly excluded"

    def test_linkedin_scam_caught(self):
        """A scam LinkedIn job should be excluded."""
        job = self.make_job(
            title="Freshers Bulk Hiring",
            company="BPO Services Ltd",
            description="Immediate joining for data entry! Work from home. WhatsApp us.",
        )
        settings = make_exclusion_settings()
        spec = self._build_linkedin_exclusion_spec(settings)
        assert spec.is_satisfied_by(job), "LinkedIn scam job not caught"

    def test_linkedin_scam_disabled(self):
        """When scam filter is disabled, LinkedInScamSpecification shouldn't fire."""
        job = self.make_job(
            title="Freshers Bulk Hiring",
            company="BPO Services Ltd",
            description="Immediate joining for data entry! Work from home.",
        )
        settings = make_exclusion_settings(enable_scam_filter=False)
        spec = self._build_linkedin_exclusion_spec(settings)
        assert not spec.is_satisfied_by(job), "LinkedIn scam job caught despite filter disabled"

    def test_linkedin_post_fetch_recheck(self):
        """Simulate LinkedIn agent's post-fetch re-check flow (line 526-543)."""
        from src.linked_agent.models.rules import (
            CompanyExclusionSpecification as LinkedinCompanyExclusion,
            TitleExclusionSpecification as LinkedinTitleExclusion,
            DescriptionExclusionSpecification as LinkedinDescExclusion,
            AuthenticityExclusionSpecification as LinkedinAuthExclusion,
            LinkedInScamSpecification,
        )

        settings = make_exclusion_settings()
        base = (
            LinkedinCompanyExclusion(settings.companies)
            | LinkedinTitleExclusion(settings.title_keywords)
            | LinkedinDescExclusion(settings.description_keywords)
            | LinkedinAuthExclusion(
                settings.fake_company_blocklist,
                settings.max_openings_without_logo,
            )
        )
        spec = base | LinkedInScamSpecification()

        # Before description fetch — should NOT flag (empty description)
        job_before = self.make_job(
            title="Data Entry",
            company="Some Corp",
            description="",
        )
        # LinkedInScamSpecification with empty description might still match
        # on title-level patterns. Let's check what happens.
        excluded_before = spec.is_satisfied_by(job_before)

        # After description fetch — should flag (now has scam keywords)
        job_after = self.make_job(
            title="Data Entry",
            company="Some Corp",
            description="Immediate hiring data entry. WhatsApp your resume. Registration fee required.",
        )
        excluded_after = spec.is_satisfied_by(job_after)

        # It's acceptable if before-fetch doesn't exclude (empty desc) or does
        # (if title matches). But after-fetch MUST exclude.
        assert excluded_after, "LinkedIn scam not caught after description fetch"
        # Log the before-fetch result for diagnostics
        if excluded_before:
            print("[diagnostic] LinkedIn job excluded even before description fetch (title match)")


# ===========================================================================
# SCENARIO 17: C++ short description (S9 regression)
# ===========================================================================
class TestCppShortDescription:
    """C++ in a short description should not trigger S9."""

    def test_s9_does_not_fire_for_cpp(self):
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="17",
            title="C++ Developer",
            company="ProductInc",
            url="",
            description="C++ developer needed",
        )
        score = compute_scam_score(job)
        has_s9 = any("No tech skills" in r for r in score.reasons)
        assert not has_s9, "S9 fired for C++ short description (false positive)"
        # G3 requires desc > 400 chars with 2+ tech categories, not triggered here


# ===========================================================================
# SCENARIO 18: Social media @handle vs email (regression)
# ===========================================================================
class TestEmailDoesNotTriggerS25:
    """Email addresses should not trigger S25 social media signal."""

    @pytest.mark.parametrize("desc", [
        "hr@gmail.com",
        "contact@yahoo.com",
        "resume@outlook.com",
        "info@rediffmail.com",
        "careers@protonmail.com",
    ])
    def test_email_does_not_trigger_s25(self, desc):
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="18",
            title="Developer",
            company="Some Corp",
            url="",
            description=desc,
        )
        score = compute_scam_score(job)
        has_s25 = any("Social media handle" in r for r in score.reasons)
        assert not has_s25, f"S25 triggered for email: {desc}"

    @pytest.mark.parametrize("desc", [
        "t.me/jobchannel",
        "Contact us on Instagram @company_handle",
        "Join our Telegram group @jobs_channel",
        "wa.me/1234567890",
        "join our whatsapp group",
    ])
    def test_social_media_triggers_s25(self, desc):
        from src.naukri_agent.models.entities import Job

        job = Job(
            naukri_job_id="18b",
            title="Developer",
            company="Some Corp",
            url="",
            description=desc,
        )
        score = compute_scam_score(job)
        has_s25 = any("Social media handle" in r for r in score.reasons)
        assert has_s25, f"S25 did NOT trigger for social media: {desc}"
