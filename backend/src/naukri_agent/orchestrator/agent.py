"""
Main orchestration engine for the Naukri Agent.

Ties together all components (AI, browser, database) into a cohesive
automation loop that searches for jobs, scores them, and applies to
matching positions.

Orchestration flow:
1. Load config & initialize all components
2. Parse resume (or load cached profile)
3. Launch browser & login to Naukri
4. Search for jobs across all keyword × location combinations
5. For each job:
   a. Check if already applied → skip
   b. Check daily cap → stop if reached
   c. Check exclusion filters → skip if excluded
   d. Scrape full job description
   e. AI match scoring → skip if below threshold
   f. Apply to job (handle screening questions)
   g. Log result to database
   h. Random delay before next application
6. Print run summary
7. Save session state & close browser
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import heapq
import json
import signal
import sys
from collections.abc import Callable
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from src.naukri_agent.ai.similarity import VectorSimilarityFilter
from src.naukri_agent.browser.apply import JobApplier
from src.naukri_agent.browser.login import LoginHandler
from src.naukri_agent.browser.profile import ProfileRefresher
from src.naukri_agent.browser.search import JobSearcher
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.domain.entities import Job, JobApplication, ResumeProfile
from src.naukri_agent.core.domain.specifications import (
    BigCompanyAllowlistSpecification,
    CompanyExclusionSpecification,
    DescriptionExclusionSpecification,
    JobSpecification,
    TitleExclusionSpecification,
)
from src.naukri_agent.core.exceptions import LLMAPIError, LLMQuotaExceededError
from src.naukri_agent.core.interfaces import (
    IBrowserEngine,
    IBrowserInteractions,
    IJobMatcher,
    ILLMProvider,
    IProgressReporter,
    IQuestionAnswerer,
    IRepository,
    IResumeParser,
)
from src.naukri_agent.core.progress import (
    NullProgressReporter,
    counters_payload,
    job_event_payload,
)
from src.naukri_agent.orchestrator.factory import DependencyFactory
from src.naukri_agent.utils.helpers import TimeUtility
from src.naukri_agent.utils.company_legitimacy import EmployerLegitimacyFilter
from src.naukri_agent.utils.filters import JobQualityFilter
from src.naukri_agent.utils.job_metadata import merge_job_metadata
from src.naukri_agent.utils.logger import (
    console,
    get_logger,
    log_error,
    log_info,
    log_step,
    log_success,
    log_warning,
    setup_logging,
)

logger = get_logger(__name__)


class NaukriAgent:
    """
    The main orchestration engine that coordinates all subsystems.

    Usage:
        factory = DependencyFactory(settings)
        agent = NaukriAgent(factory)
        await agent.run()
    """

    _factory: DependencyFactory | None
    _settings: Settings
    _repo: IRepository
    _engine: IBrowserEngine
    _interactions: IBrowserInteractions
    _llm: ILLMProvider
    _resume_parser: IResumeParser
    _login_handler: LoginHandler
    _job_searcher: JobSearcher
    _job_matcher: IJobMatcher
    _question_answerer_factory: Callable[[ResumeProfile], IQuestionAnswerer]
    _job_applier_factory: Callable[[IQuestionAnswerer], JobApplier]
    _profile_refresher: ProfileRefresher
    _resume_profile: ResumeProfile | None

    def __init__(
        self,
        factory: DependencyFactory | None = None,
        *,
        settings: Settings | None = None,
        repository: IRepository | None = None,
        browser_engine: IBrowserEngine | None = None,
        browser_interactions: IBrowserInteractions | None = None,
        llm_provider: ILLMProvider | None = None,
        resume_parser: IResumeParser | None = None,
        login_handler: LoginHandler | None = None,
        job_searcher: JobSearcher | None = None,
        job_matcher: IJobMatcher | None = None,
        question_answerer_factory: Callable[[ResumeProfile], IQuestionAnswerer] | None = None,
        job_applier_factory: Callable[[IQuestionAnswerer], JobApplier] | None = None,
        profile_refresher: ProfileRefresher | None = None,
        progress_reporter: IProgressReporter | None = None,
    ) -> None:
        self._factory = factory

        # Settings
        _settings = settings or (factory.get_settings() if factory else None)
        if not _settings:
            raise ValueError("Either factory or settings must be provided.")
        self._settings = _settings

        # Repository
        _repo = repository or (factory.get_repository() if factory else None)
        if not _repo:
            raise ValueError("Repository is required.")
        self._repo = _repo

        # Browser Engine
        _engine = browser_engine or (factory.get_browser_engine() if factory else None)
        if not _engine:
            raise ValueError("Browser engine is required.")
        self._engine = _engine

        # Browser Interactions
        _interactions = browser_interactions or (
            factory.get_browser_interactions() if factory else None
        )
        if not _interactions:
            raise ValueError("Browser interactions are required.")
        self._interactions = _interactions

        # LLM Provider
        _llm = llm_provider or (factory.get_llm_provider() if factory else None)
        if not _llm:
            raise ValueError("LLM provider is required.")
        self._llm = _llm

        # Resume Parser
        _resume_parser = resume_parser or (factory.create_resume_parser() if factory else None)
        if not _resume_parser:
            raise ValueError("Resume parser is required.")
        self._resume_parser = _resume_parser

        # Login Handler
        _login_handler = login_handler or (factory.create_login_handler() if factory else None)
        if not _login_handler:
            raise ValueError("Login handler is required.")
        self._login_handler = _login_handler

        # Job Searcher
        _job_searcher = job_searcher or (factory.create_job_searcher() if factory else None)
        if not _job_searcher:
            raise ValueError("Job searcher is required.")
        self._job_searcher = _job_searcher

        # Job Matcher
        _job_matcher = job_matcher or (factory.create_job_matcher() if factory else None)
        if not _job_matcher:
            raise ValueError("Job matcher is required.")
        self._job_matcher = _job_matcher

        # Factories & Refresher
        if question_answerer_factory:
            self._question_answerer_factory = question_answerer_factory
        elif factory:
            self._question_answerer_factory = lambda profile: factory.create_question_answerer(
                profile
            )
        else:
            raise ValueError("Question answerer factory is required.")

        if job_applier_factory:
            self._job_applier_factory = job_applier_factory
        elif factory:
            self._job_applier_factory = lambda qa: factory.create_job_applier(qa)
        else:
            raise ValueError("Job applier factory is required.")

        _profile_refresher = profile_refresher or (
            factory.create_profile_refresher() if factory else None
        )
        if not _profile_refresher:
            raise ValueError("Profile refresher is required.")
        self._profile_refresher = _profile_refresher

        self._resume_profile = None
        self._run_log_id: int | None = None
        self._interrupted = False

        # Counters
        self._jobs_found = 0
        self._jobs_applied = 0
        self._jobs_skipped = 0
        self._jobs_failed = 0
        self._applied_jobs_this_run: list[dict] = []

        # Job Exclusions Specification
        self._exclusion_spec: JobSpecification | None = None
        self._big_company_spec: BigCompanyAllowlistSpecification | None = None
        self._employer_filter: EmployerLegitimacyFilter | None = None
        self._quality_filter: JobQualityFilter | None = None
        self._progress = progress_reporter or NullProgressReporter()
        self._phase = "idle"
        self._run_errored = False

    async def _emit(self, event_type: str, data: dict | None = None) -> None:
        payload = dict(data or {})
        if self._run_log_id is not None:
            payload["run_id"] = self._run_log_id
        await self._progress.emit(event_type, payload)

    async def _emit_job(self, job: Job, status: str, **extra) -> None:
        await self._emit("job_updated", job_event_payload(job, status, **extra))

    async def _emit_counters(self, **extra) -> None:
        daily_cap = self._settings.application.daily_cap
        daily_applied = getattr(self, "_daily_applied", 0)
        payload = {
            "jobs_found": self._jobs_found,
            "jobs_applied": self._jobs_applied,
            "jobs_skipped": self._jobs_skipped,
            "jobs_failed": self._jobs_failed,
            "daily_cap_remaining": max(0, daily_cap - daily_applied),
            "phase": self._phase,
        }
        payload.update(extra)
        await self._emit(
            "counters_updated",
            counters_payload(self._run_log_id or 0, **payload),
        )

    def set_progress_reporter(self, reporter: IProgressReporter) -> None:
        self._progress = reporter
        if hasattr(self._job_searcher, "set_progress_reporter"):
            self._job_searcher.set_progress_reporter(reporter, lambda: self._run_log_id)

    async def run(self, dry_run: bool = False) -> None:
        """
        Execute the full agent loop.

        Args:
            dry_run: If True, score jobs but don't actually apply.
        """
        if dry_run:
            self._settings.application.dry_run = True

        # Setup
        self._print_banner()
        setup_logging(
            level=self._settings.logging.level,
            log_to_file=self._settings.logging.log_to_file,
            log_dir=str(self._settings.project_root / self._settings.logging.log_dir),
        )
        self._settings.ensure_dirs()

        # Register signal handler for graceful shutdown
        self._register_signal_handlers()

        self._phase = "starting"
        await self._emit("run_started", {"dry_run": dry_run})

        try:
            # Step 1: Initialize run log
            log_info("Starting agent run...")
            if self._repo:
                await self._repo.initialize()
                self._run_log_id = await self._repo.create_run_log(
                    search_keywords=self._settings.search.keywords
                )
                if hasattr(self._job_searcher, "set_progress_reporter"):
                    self._job_searcher.set_progress_reporter(
                        self._progress, lambda: self._run_log_id
                    )

            # Step 2: Parse resume
            self._phase = "parsing_resume"
            await self._emit_counters()
            await self._parse_resume()
            if not self._resume_profile:
                log_error("Cannot proceed without a parsed resume profile.")
                self._run_errored = True
                self._phase = "error"
                await self._emit("run_error", {"message": "Resume profile not available"})
                return
            await self._emit("resume_parsed", {"name": self._resume_profile.name or ""})

            # Step 3: Launch browser & login
            self._phase = "logging_in"
            await self._emit_counters()
            await self._engine.launch()
            await self._emit("login_started", {})

            login_handler = self._login_handler
            if not login_handler:
                raise RuntimeError("LoginHandler not configured.")
            login_success = await login_handler.login()
            if not login_success:
                log_error("Login failed. Cannot proceed.")
                self._run_errored = True
                self._phase = "error"
                await self._emit("login_failed", {})
                await self._send_alert(
                    "run",
                    RuntimeError("Login failed — could not authenticate with Naukri.com."),
                )
                return
            await self._emit("login_success", {})

            # Step 4: Search for jobs
            self._phase = "searching"
            await self._emit_counters()
            await self._emit("search_started", {})
            searcher = self._job_searcher
            if not searcher:
                raise RuntimeError("JobSearcher not configured.")
            jobs = await searcher.search_all()
            self._jobs_found = len(jobs)
            await self._emit("search_completed", {"jobs_found": self._jobs_found})
            await self._emit_counters(jobs_found=self._jobs_found)

            if not jobs:
                log_warning("No jobs found matching your search criteria.")
                return

            log_success(f"Found {len(jobs)} candidate jobs. Starting evaluation...")

            # Build the composed job exclusion specifications
            exclusions = self._settings.exclusions
            self._exclusion_spec = (
                CompanyExclusionSpecification(exclusions.companies)
                | TitleExclusionSpecification(exclusions.title_keywords)
                | DescriptionExclusionSpecification(exclusions.description_keywords)
            )
            big_companies = self._settings.application.big_companies
            self._big_company_spec = BigCompanyAllowlistSpecification(big_companies)
            if not big_companies:
                log_warning(
                    "application.big_companies allowlist is empty — all jobs will be skipped."
                )
            self._quality_filter = JobQualityFilter(
                require_verified=self._settings.application.require_verified_job,
                min_company_rating=self._settings.application.min_company_rating,
            )
            self._employer_filter = EmployerLegitimacyFilter(
                big_companies=big_companies,
                verify_online=self._settings.application.verify_employer_online,
            )

            # Step 5: Initialize AI components
            matcher = self._job_matcher
            if not matcher:
                raise RuntimeError("JobMatcher not configured.")
            if self._question_answerer_factory is None:
                raise RuntimeError("QuestionAnswerer factory not configured.")
            if self._job_applier_factory is None:
                raise RuntimeError("JobApplier factory not configured.")

            if self._resume_profile is None:
                raise RuntimeError("Resume profile not loaded.")

            qa = self._question_answerer_factory(self._resume_profile)
            applier = self._job_applier_factory(qa)

            resume_text = (
                self._resume_profile.skills
                + [self._resume_profile.current_title]
                + [self._resume_profile.summary]
            )
            vector_filter = VectorSimilarityFilter(resume_text)

            # Step 6: Process each job using Priority Queue Max-Heap
            self._phase = "processing"
            await self._emit_counters(jobs_found=self._jobs_found, total_queued=len(jobs))
            await self._process_jobs(jobs, matcher, applier, searcher, vector_filter)

        except KeyboardInterrupt:
            log_warning("Agent interrupted by user (Ctrl+C)")
            self._interrupted = True
        except Exception as e:
            log_error(f"Agent error: {e}")
            logger.exception("Agent fatal error")
            self._run_errored = True
            self._phase = "error"
            await self._emit("run_error", {"message": str(e)})
            await self._send_alert("run", e)
        finally:
            await self._cleanup()

    async def _parse_resume(self) -> None:
        """Parse the resume PDF and cache the structured profile."""
        resume_path = self._settings.resume.path
        if not resume_path:
            log_error("Resume path not configured. Set 'resume.path' in config.yaml")
            return

        path = Path(resume_path)
        if not path.is_absolute():
            path = self._settings.project_root / path
        if not path.exists():
            log_error(f"Resume file not found: {path}")
            return

        parser = self._resume_parser
        if not parser:
            raise RuntimeError("ResumeParser not configured.")
        self._resume_profile = await parser.parse(str(path))

        if self._resume_profile:
            console.print(
                Panel(
                    f"[bold]{self._resume_profile.name or 'Unknown'}[/bold]\n"
                    f"Skills: {', '.join(self._resume_profile.skills[:10])}...\n"
                    f"Experience: {self._resume_profile.total_experience_years} years\n"
                    f"Title: {self._resume_profile.current_title or 'N/A'}",
                    title="📄 Resume Profile",
                    border_style="cyan",
                )
            )

    async def _process_jobs(
        self,
        jobs: list[Job],
        matcher: IJobMatcher,
        applier: JobApplier,
        searcher: JobSearcher,
        vector_filter: VectorSimilarityFilter,
    ) -> None:
        """
        Process jobs sequentially: Rank in Max-Heap, pre-filter with TF-IDF,
        AI Match, and Apply. Prevents concurrency issues on the shared browser page.
        """
        log_info("Building Max-Heap Priority Queue for optimal processing order...")
        assert self._resume_profile is not None, (
            "_process_jobs() requires a parsed resume profile; run() must "
            "check and return early before calling this."
        )
        resume_profile = self._resume_profile
        job_queue: list[tuple[float, int, Job]] = []
        for idx, job in enumerate(jobs):
            text_to_score = f"{job.title} {job.company} {job.skills}"
            score = vector_filter.get_similarity_score(text_to_score)

            posted = str(job.posted_date).lower()
            if "just now" in posted or "hour" in posted or "today" in posted or "1 day" in posted:
                score += 0.05

            heapq.heappush(job_queue, (-score, idx, job))

        total_jobs = len(job_queue)
        self._daily_applied = await self._repo.get_today_application_count() if self._repo else 0
        processed_count = 0

        for _, _, job in job_queue:
            await self._emit_job(job, "queued")

        while job_queue:
            if self._interrupted:
                break

            neg_score, idx, job = heapq.heappop(job_queue)
            initial_score = -neg_score

            remaining = self._settings.application.daily_cap - self._daily_applied
            if remaining <= 0:
                log_warning(
                    f"Daily application cap reached ({self._settings.application.daily_cap}). Stopping."
                )
                break

            processed_count += 1
            await self._emit_job(job, "processing", heuristic_score=initial_score)
            await self._emit_counters(
                jobs_found=self._jobs_found,
                processed_count=processed_count,
                total_queued=total_jobs,
            )
            log_step(
                processed_count,
                total_jobs,
                f"{job.title} @ {job.company} (Heuristic: {initial_score:.2f})",
            )

            # Deduplication
            if self._repo and self._repo.is_already_applied(job.naukri_job_id):
                self._jobs_skipped += 1
                await self._emit_job(job, "skipped_already_applied", heuristic_score=initial_score)
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    processed_count=processed_count,
                    total_queued=total_jobs,
                )
                continue

            # Exclusion filters
            if self._is_excluded(job):
                self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    "skipped_excluded",
                    heuristic_score=initial_score,
                    reason="Excluded by company/title/description filter",
                )
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    processed_count=processed_count,
                    total_queued=total_jobs,
                )
                continue

            # Big-company allowlist gate
            if not self._is_big_company(job):
                self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    ApplicationStatus.SKIPPED_NOT_BIG_COMPANY,
                    heuristic_score=initial_score,
                    reason="Company not in big_companies allowlist",
                )
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    processed_count=processed_count,
                    total_queued=total_jobs,
                )
                continue

            # Check browser status before interacting
            if not self._engine.is_alive():
                log_warning("Browser disconnected! Restarting browser engine...")
                with contextlib.suppress(Exception):
                    await self._engine.close()
                await self._engine.launch()
                try:
                    login_handler = self._login_handler
                    if not login_handler:
                        raise RuntimeError("LoginHandler not configured.")
                    await login_handler.login()
                except Exception as e:
                    logger.error(f"Failed to re-login after restart: {e}")

            # Get description, skills, quality metadata, and apply type from the job page
            needs_detail_page = (
                not job.description
                or job.is_verified is None
                or job.company_rating is None
                or job.is_external_apply is None
                or job.hiring_for is None
                or job.is_consultant_post is None
            )
            if needs_detail_page:
                details = await searcher.get_job_description(job.url)
                if details.get("description"):
                    job.description = details["description"]
                if details.get("skills"):
                    job.skills = details["skills"]
                merge_job_metadata(
                    job,
                    rating=details.get("company_rating"),
                    verified=details.get("is_verified"),
                    is_external_apply=details.get("is_external_apply"),
                    external_apply_url=details.get("external_apply_url"),
                    hiring_for=details.get("hiring_for"),
                    is_consultant_post=details.get("is_consultant_post"),
                )
                if not self._interactions:
                    raise RuntimeError("BrowserInteractions not configured.")
                await self._interactions.action_delay()

            if self._employer_filter:
                passes_employer, employer_reason = await self._employer_filter.evaluate(job)
                if not passes_employer:
                    log_warning(
                        f"Skipping {job.title} @ {job.company}: {employer_reason}"
                    )
                    self._jobs_skipped += 1
                    await self._emit_job(
                        job,
                        ApplicationStatus.SKIPPED_CONSULTANCY_RECRUITER,
                        heuristic_score=initial_score,
                        reason=employer_reason,
                    )
                    await self._emit_counters(
                        jobs_found=self._jobs_found,
                        processed_count=processed_count,
                        total_queued=total_jobs,
                    )
                    continue

            if job.is_external_apply:
                self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    ApplicationStatus.EXTERNAL_APPLY,
                    heuristic_score=initial_score,
                    reason="External apply — apply on company site",
                )
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    processed_count=processed_count,
                    total_queued=total_jobs,
                )
                continue

            if self._quality_filter:
                passes_quality, skip_reason = self._quality_filter.evaluate(job)
                if not passes_quality:
                    log_warning(
                        f"Skipping {job.title} @ {job.company}: {skip_reason}"
                    )
                    self._jobs_skipped += 1
                    await self._emit_job(
                        job,
                        ApplicationStatus.SKIPPED_LOW_COMPANY_RATING
                        if "rating" in skip_reason.lower()
                        else "skipped_quality",
                        heuristic_score=initial_score,
                        reason=skip_reason,
                    )
                    await self._emit_counters(
                        jobs_found=self._jobs_found,
                        processed_count=processed_count,
                        total_queued=total_jobs,
                    )
                    continue

            # Second similarity filter (using description)
            full_text = f"{job.title} {job.skills} {job.description}"
            full_sim_score = vector_filter.get_similarity_score(full_text)

            if full_sim_score < 0.03:
                self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    "skipped_similarity",
                    heuristic_score=initial_score,
                    reason="TF-IDF similarity below threshold",
                )
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    processed_count=processed_count,
                    total_queued=total_jobs,
                )
                continue

            # AI Matching (pace to respect Gemini free tier limits)
            await self._emit_job(job, "matching", heuristic_score=initial_score)
            log_info("Pacing AI requests (waiting 6.5s) to avoid Google limits...")
            await asyncio.sleep(6.5)

            try:
                match_result = await matcher.match(resume_profile, job)
            except (LLMQuotaExceededError, LLMAPIError) as e:
                # Determine if it's a daily quota error or any general API failure (like 503)
                is_daily = isinstance(e, LLMQuotaExceededError) and e.is_daily_quota

                # Fallback to model if configured (works for both daily quota exhaustion and model failures/503s)
                if self._settings.ai.fallback_model:
                    fallback_model = self._settings.ai.fallback_model
                    reason = (
                        "daily request quota is exhausted"
                        if is_daily
                        else f"failed with error: {e}"
                    )
                    log_warning(f"⚠️  Primary model '{self._settings.ai.model}' {reason}.")
                    log_success(
                        f"✅ Switching to fallback model '{fallback_model}' and continuing run..."
                    )

                    # Update active model name
                    llm_provider = self._llm
                    if not llm_provider:
                        raise RuntimeError("LLMProvider not configured.") from e
                    if hasattr(llm_provider, "set_model"):
                        llm_provider.set_model(fallback_model)

                    # Update settings
                    self._settings.ai.model = fallback_model
                    self._settings.ai.fallback_model = None  # Prevent infinite fallback loop

                    # Retry current match once
                    try:
                        match_result = await matcher.match(resume_profile, job)
                    except Exception as fallback_err:
                        logger.error(f"AI Match failed on fallback model: {fallback_err}")
                        self._jobs_failed += 1
                        continue
                else:
                    if isinstance(e, LLMQuotaExceededError):
                        if e.is_daily_quota:
                            log_error(str(e))
                            if self._settings.ai.abort_on_quota:
                                log_error(
                                    "⚠️  Gemini's daily request quota is exhausted — stopping "
                                    "the run here instead of marking every remaining job as a "
                                    "non-match."
                                )
                                await self._send_alert(
                                    "run",
                                    e,
                                    extra_context=(
                                        f"Model: {self._settings.ai.model}\n"
                                        f"Jobs processed so far: applied={self._jobs_applied}, "
                                        f"failed={self._jobs_failed}, skipped={self._jobs_skipped}"
                                    ),
                                )
                                self._interrupted = True
                                break
                            else:
                                log_warning(
                                    f"⚠️  Gemini's daily request quota is exhausted for model '{self._settings.ai.model}', "
                                    "but continuing run (abort_on_quota is False)."
                                )
                                self._jobs_failed += 1
                                continue
                        else:
                            log_error(
                                "⚠️  Gemini rate limit hit repeatedly — stopping the run "
                                "to avoid wasting further requests."
                            )
                            log_error(str(e))
                            self._interrupted = True
                            break
                    else:
                        log_error(f"⚠️  Gemini API error occurred: {e}")
                        self._jobs_failed += 1
                        continue
            except Exception as e:
                logger.error(f"AI Match failed: {e}")
                self._jobs_failed += 1
                continue

            # Save job in database
            db_job = None
            if self._repo:
                db_job = await self._repo.save_job(
                    naukri_job_id=job.naukri_job_id,
                    title=job.title,
                    company=job.company,
                    url=job.url,
                    location=job.location,
                    experience=job.experience,
                    salary=job.salary,
                    description=job.description,
                    skills=job.skills,
                    posted_date=job.posted_date,
                )
                assert db_job.id is not None

            match_score = match_result.match_score
            should_apply = match_result.should_apply

            if not should_apply:
                if self._repo and db_job:
                    assert db_job.id is not None
                    await self._repo.save_application(
                        job_id=db_job.id,
                        match_score=match_score,
                        status=ApplicationStatus.SKIPPED_LOW_SCORE,
                        match_reasoning=match_result.match_reasoning,
                        matching_skills=match_result.matching_skills,
                        missing_skills=match_result.missing_skills,
                    )
                self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    "skipped_low_score",
                    heuristic_score=initial_score,
                    match_score=match_score,
                    match_reasoning=match_result.match_reasoning,
                )
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    processed_count=processed_count,
                    total_queued=total_jobs,
                )
                continue

            if self._settings.application.dry_run:
                log_info(f"DRY RUN — would apply (score: {match_score})")
                if self._repo and db_job:
                    assert db_job.id is not None
                    await self._repo.save_application(
                        job_id=db_job.id,
                        match_score=match_score,
                        status=ApplicationStatus.SKIPPED_DRY_RUN,
                        match_reasoning=match_result.match_reasoning,
                        matching_skills=match_result.matching_skills,
                        missing_skills=match_result.missing_skills,
                    )
                self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    "skipped_dry_run",
                    heuristic_score=initial_score,
                    match_score=match_score,
                    match_reasoning=match_result.match_reasoning,
                )
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    processed_count=processed_count,
                    total_queued=total_jobs,
                )
                continue

            # Navigation validation
            page = self._engine.page
            if job.url not in page.url:
                try:
                    await page.goto(job.url, wait_until="domcontentloaded", timeout=60000)
                    if not self._interactions:
                        raise RuntimeError("BrowserInteractions not configured.")
                    await self._interactions.wait_for_navigation_complete()
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Failed to navigate to job page {job.url}: {e}")
                    if self._repo and db_job:
                        assert db_job.id is not None
                        await self._repo.save_application(
                            job_id=db_job.id,
                            match_score=match_score,
                            status=ApplicationStatus.FAILED,
                            match_reasoning=match_result.match_reasoning,
                            matching_skills=match_result.matching_skills,
                            missing_skills=match_result.missing_skills,
                            error_message=f"Navigation failed: {e}",
                        )
                    self._jobs_failed += 1
                    await self._emit_job(
                        job,
                        "failed",
                        heuristic_score=initial_score,
                        match_score=match_score,
                        reason=f"Navigation failed: {e}",
                    )
                    await self._emit_counters(
                        jobs_found=self._jobs_found,
                        processed_count=processed_count,
                        total_queued=total_jobs,
                    )
                    continue

            # Run apply flow
            await self._emit_job(
                job,
                "applying",
                heuristic_score=initial_score,
                match_score=match_score,
                match_reasoning=match_result.match_reasoning,
            )
            apply_result = await applier.apply_to_job(job)
            status = apply_result.get("status", ApplicationStatus.FAILED)
            error_msg = apply_result.get("error_message", "")

            if self._repo and db_job:
                assert db_job.id is not None
                await self._repo.save_application(
                    job_id=db_job.id,
                    match_score=match_score,
                    status=status,
                    match_reasoning=match_result.match_reasoning,
                    matching_skills=match_result.matching_skills,
                    missing_skills=match_result.missing_skills,
                    error_message=error_msg,
                )

            if status == ApplicationStatus.APPLIED:
                self._jobs_applied += 1
                self._daily_applied += 1
                await self._emit_job(
                    job,
                    "applied",
                    heuristic_score=initial_score,
                    match_score=match_score,
                    match_reasoning=match_result.match_reasoning,
                )
                self._applied_jobs_this_run.append(
                    {
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "experience": job.experience,
                        "salary": job.salary,
                        "match_score": match_score,
                        "url": job.url,
                        "skills": job.skills,
                    }
                )
                await TimeUtility.random_delay(
                    self._settings.application.delay_between_applies_min,
                    self._settings.application.delay_between_applies_max,
                )
            elif status.startswith("skipped"):
                self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    status,
                    heuristic_score=initial_score,
                    match_score=match_score,
                    match_reasoning=match_result.match_reasoning,
                    reason=error_msg or None,
                )
            else:
                self._jobs_failed += 1
                await self._emit_job(
                    job,
                    "failed",
                    heuristic_score=initial_score,
                    match_score=match_score,
                    match_reasoning=match_result.match_reasoning,
                    reason=error_msg or None,
                )
            await self._emit_counters(
                jobs_found=self._jobs_found,
                processed_count=processed_count,
                total_queued=total_jobs,
            )

    def _is_excluded(self, job: Job) -> bool:
        """Check if a job matches any exclusion specifications."""
        if not self._exclusion_spec:
            return False
        return self._exclusion_spec.is_satisfied_by(job)

    def _is_big_company(self, job: Job) -> bool:
        """Check if a job's company is in the big-company allowlist."""
        if not self._big_company_spec:
            return False
        return self._big_company_spec.is_satisfied_by(job)

    async def _cleanup(self) -> None:
        """Save state, update run log, print summary, and close browser."""
        # Update run log
        if self._repo and self._run_log_id:
            status = (
                "interrupted"
                if self._interrupted
                else "error"
                if self._run_errored
                else "completed"
            )
            await self._repo.update_run_log(
                run_log_id=self._run_log_id,
                jobs_found=self._jobs_found,
                jobs_applied=self._jobs_applied,
                jobs_skipped=self._jobs_skipped,
                jobs_failed=self._jobs_failed,
                status=status,
            )

        if self._run_errored:
            self._phase = "error"
        elif self._interrupted:
            self._phase = "interrupted"
        else:
            self._phase = "completed"

        if self._run_errored:
            pass
        elif self._interrupted:
            await self._emit(
                "run_interrupted",
                {
                    "jobs_found": self._jobs_found,
                    "jobs_applied": self._jobs_applied,
                    "jobs_skipped": self._jobs_skipped,
                    "jobs_failed": self._jobs_failed,
                },
            )
        else:
            await self._emit(
                "run_completed",
                {
                    "jobs_found": self._jobs_found,
                    "jobs_applied": self._jobs_applied,
                    "jobs_skipped": self._jobs_skipped,
                    "jobs_failed": self._jobs_failed,
                },
            )
        await self._emit_counters(
            jobs_found=self._jobs_found,
            processed_count=self._jobs_applied + self._jobs_skipped + self._jobs_failed,
        )

        if self._run_log_id is not None:
            from src.naukri_agent.core.progress import InMemoryEventBus

            if isinstance(self._progress, InMemoryEventBus):
                await self._progress.close_subscribers(self._run_log_id)

        # Track metrics
        from src.naukri_agent.utils.telemetry import MetricsTracker

        metrics = MetricsTracker(str(self._settings.project_root / self._settings.logging.log_dir))
        metrics.record_run(self._jobs_applied, self._jobs_failed)

        # Print summary and save applied-jobs report
        self._save_applied_jobs_report()
        self._print_summary()

        # Close browser
        if self._engine:
            try:
                await self._engine.close()
            except Exception as e:
                logger.debug(f"Browser close error: {e}")

    def _print_banner(self) -> None:
        """Print the agent startup banner."""
        console.print(
            Panel(
                "[bold cyan]🤖 Naukri.com AI Job Application Agent[/bold cyan]\n\n"
                f"  Keywords: {', '.join(self._settings.search.keywords)}\n"
                f"  Locations: {', '.join(self._settings.search.locations)}\n"
                f"  Daily Cap: {self._settings.application.daily_cap}\n"
                f"  Match Threshold: {self._settings.application.match_score_threshold}%\n"
                f"  Dry Run: {'Yes' if self._settings.application.dry_run else 'No'}\n"
                f"  AI Model: {self._settings.ai.model}",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    def _save_applied_jobs_report(self) -> None:
        """Persist applied job details from this run to a JSON file."""
        if not self._applied_jobs_this_run:
            return

        from datetime import UTC, datetime

        log_dir = self._settings.project_root / self._settings.logging.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        report_path = log_dir / f"applied_jobs_{timestamp}.json"

        report = {
            "run_log_id": self._run_log_id,
            "applied_count": len(self._applied_jobs_this_run),
            "jobs": self._applied_jobs_this_run,
        }
        try:
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log_info(f"Applied jobs report saved to {report_path}")
        except OSError as e:
            log_warning(f"Could not save applied jobs report: {e}")

    def _print_summary(self) -> None:
        """Print the end-of-run summary table."""
        table = Table(
            title="📊 Run Summary",
            show_header=True,
            header_style="bold magenta",
            border_style="dim",
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("Jobs Found", str(self._jobs_found))
        table.add_row("Jobs Applied", f"[bold green]{self._jobs_applied}[/bold green]")
        table.add_row("Jobs Skipped", str(self._jobs_skipped))
        table.add_row("Jobs Failed", str(self._jobs_failed))

        console.print()
        console.print(table)

        if self._applied_jobs_this_run:
            console.print()
            applied_table = Table(
                title="✅ Jobs Applied This Run",
                show_header=True,
                header_style="bold green",
                border_style="dim",
                show_lines=True,
            )
            applied_table.add_column("#", style="dim", justify="right", width=3)
            applied_table.add_column("Role", style="cyan", max_width=28)
            applied_table.add_column("Company", style="white", max_width=22)
            applied_table.add_column("Location", style="dim", max_width=14)
            applied_table.add_column("Exp", style="dim", max_width=10)
            applied_table.add_column("Salary", style="dim", max_width=12)
            applied_table.add_column("Score", justify="right", width=5)

            for idx, job in enumerate(self._applied_jobs_this_run, start=1):
                score = job["match_score"]
                score_style = "green" if score >= 80 else "yellow" if score >= 60 else "red"
                applied_table.add_row(
                    str(idx),
                    job["title"][:28],
                    job["company"][:22],
                    job["location"][:14] or "—",
                    job["experience"][:10] or "—",
                    job["salary"][:12] or "—",
                    f"[{score_style}]{score:.0f}[/{score_style}]",
                )
            console.print(applied_table)

        console.print()

    def _register_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM handlers for graceful shutdown."""

        def handle_signal(signum, frame):
            log_warning("Received shutdown signal. Cleaning up...")
            self._interrupted = True

        if sys.platform != "win32":
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        else:
            signal.signal(signal.SIGINT, handle_signal)

    async def _send_alert(
        self,
        task_name: str,
        exception: BaseException,
        extra_context: str = "",
    ) -> None:
        """Best-effort email alert — never raises."""
        try:
            if not self._settings.alerts.enabled:
                return
            sender = self._settings.naukri.gmail_otp_email
            password = self._settings.naukri.gmail_app_password
            if not sender or not password:
                return

            from src.naukri_agent.utils.email_notifier import EmailAlertNotifier

            notifier = EmailAlertNotifier(
                sender_email=sender,
                app_password=password,
                recipient_email=self._settings.alerts.recipient_email,
                cooldown_minutes=self._settings.alerts.cooldown_minutes,
                cooldown_dir=str(self._settings.project_root / self._settings.logging.log_dir),
            )
            await notifier.send_alert(task_name, exception, extra_context)
        except Exception as alert_err:
            logger.warning(f"Could not send failure alert: {alert_err}")

    # -----------------------------------------------------------------------
    # Public utility methods (for CLI subcommands)
    # -----------------------------------------------------------------------
    async def parse_resume_only(self, resume_path: str) -> ResumeProfile | None:
        """Parse a resume and print the result without running the agent."""
        parser = self._resume_parser
        if not parser:
            raise RuntimeError("ResumeParser not configured.")
        profile = await parser.parse(resume_path)

        if profile:
            profile_dict = dataclasses.asdict(profile)
            console.print_json(json.dumps(profile_dict, indent=2, ensure_ascii=False))
        return profile

    async def test_match(self, job_url: str) -> JobApplication | None:
        """
        Test matching against a specific job URL.

        Launches the browser, navigates to the job, extracts description,
        and runs the matcher.
        """
        # Parse resume first
        await self._parse_resume()
        if not self._resume_profile:
            log_error("Resume parsing failed")
            return None

        # Launch browser
        await self._engine.launch()

        # Login
        login_handler = self._login_handler
        if not login_handler:
            raise RuntimeError("LoginHandler not configured.")
        if not await login_handler.login():
            log_error("Login failed")
            await self._engine.close()
            return None

        # Get job description
        searcher = self._job_searcher
        if not searcher:
            raise RuntimeError("JobSearcher not configured.")
        details = await searcher.get_job_description(job_url)

        # Run matcher
        matcher = self._job_matcher
        if not matcher:
            raise RuntimeError("JobMatcher not configured.")
        job = Job(
            naukri_job_id="test_job",
            title="Test Job",
            company="Test Company",
            url=job_url,
            description=details.get("description", ""),
            skills=details.get("skills", ""),
            location=details.get("location_detail", ""),
            experience=details.get("experience_detail", ""),
            salary=details.get("salary_detail", ""),
        )
        result = await matcher.match(self._resume_profile, job)

        result_dict = dataclasses.asdict(result)
        console.print_json(json.dumps(result_dict, indent=2, ensure_ascii=False))

        await self._engine.close()
        return result

    async def show_status(self) -> None:
        """Display application statistics from the database."""
        setup_logging(level="INFO", log_to_file=False)

        if self._repo:
            await self._repo.initialize()

        # Stats table
        stats = (
            await self._repo.get_application_stats(days=7)
            if self._repo
            else {"total": 0, "applied": 0, "skipped": 0, "failed": 0}
        )
        stats_table = Table(
            title="📈 Application Stats (Last 7 Days)",
            show_header=True,
            header_style="bold magenta",
        )
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Count", style="green", justify="right")
        stats_table.add_row("Total", str(stats["total"]))
        stats_table.add_row("Applied", str(stats["applied"]))
        stats_table.add_row("Skipped", str(stats["skipped"]))
        stats_table.add_row("Failed", str(stats["failed"]))
        console.print(stats_table)

        # Recent applications
        recent = await self._repo.get_recent_applications(limit=15) if self._repo else []
        if recent:
            console.print()
            recent_table = Table(
                title="📋 Recent Applications",
                show_header=True,
                header_style="bold magenta",
            )
            recent_table.add_column("Job Title", style="cyan", max_width=30)
            recent_table.add_column("Company", style="white", max_width=20)
            recent_table.add_column("Score", justify="right")
            recent_table.add_column("Status", style="dim")
            recent_table.add_column("Date", style="dim")

            for app in recent:
                score = app["match_score"]
                score_style = "green" if score >= 80 else "yellow" if score >= 60 else "red"
                recent_table.add_row(
                    app["job_title"][:30],
                    app["company"][:20],
                    f"[{score_style}]{score:.0f}[/{score_style}]",
                    app["status"],
                    app["applied_at"][:10] if app["applied_at"] else "",
                )
            console.print(recent_table)

        # Run history
        runs = await self._repo.get_run_stats(limit=5) if self._repo else []
        if runs:
            console.print()
            runs_table = Table(
                title="🏃 Recent Runs",
                show_header=True,
                header_style="bold magenta",
            )
            runs_table.add_column("Date", style="dim")
            runs_table.add_column("Keywords", style="cyan", max_width=30)
            runs_table.add_column("Found", justify="right")
            runs_table.add_column("Applied", justify="right", style="green")
            runs_table.add_column("Skipped", justify="right")
            runs_table.add_column("Status", style="dim")

            for run in runs:
                runs_table.add_row(
                    run["started_at"][:16] if run["started_at"] else "",
                    ", ".join(run["keywords"])[:30],
                    str(run["found"]),
                    str(run["applied"]),
                    str(run["skipped"]),
                    run["status"],
                )
            console.print(runs_table)

    async def refresh_profile(self) -> None:
        """Automated task to log in and refresh the profile headline."""
        setup_logging(
            level=self._settings.logging.level,
            log_to_file=self._settings.logging.log_to_file,
            log_dir=str(self._settings.project_root / self._settings.logging.log_dir),
        )
        self._settings.ensure_dirs()
        self._register_signal_handlers()

        try:
            log_info("Starting Profile Refresh task...")

            # Launch browser & login
            await self._engine.launch()

            login_handler = self._login_handler
            if not login_handler:
                raise RuntimeError("LoginHandler not configured.")
            login_success = await login_handler.login()
            if not login_success:
                log_error("Login failed. Cannot proceed with profile refresh.")
                await self._send_alert(
                    "refresh-profile",
                    RuntimeError(
                        "Login failed — could not authenticate with Naukri.com "
                        "during scheduled profile refresh."
                    ),
                )
                return

            # Execute profile refresh
            refresher = self._profile_refresher
            if not refresher:
                raise RuntimeError("ProfileRefresher not configured.")
            await refresher.refresh()

        except KeyboardInterrupt:
            log_warning("Task interrupted by user (Ctrl+C)")
            self._interrupted = True
        except Exception as e:
            log_error(f"Error during profile refresh task: {e}")
            logger.exception("Profile refresh fatal error")
            await self._send_alert("refresh-profile", e)
        finally:
            if self._engine:
                try:
                    await self._engine.close()
                except Exception as e:
                    logger.debug(f"Browser close error: {e}")
