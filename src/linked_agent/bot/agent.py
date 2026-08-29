"""
Main orchestration engine for the LinkedIn Agent.

Ties together all components (AI, browser, database) into a cohesive
automation loop that searches for jobs on LinkedIn, scores them, and
applies to matching positions.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from datetime import datetime
import heapq
import json
import re
import signal
import sys
from collections.abc import Callable
from pathlib import Path

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from rich.panel import Panel
from rich.table import Table

from src.linked_agent.utils.similarity import LinkedInVectorSimilarityFilter
from src.linked_agent.browser.apply import LinkedInJobApplier
from src.linked_agent.browser.login import LinkedInLoginHandler
from src.linked_agent.browser.search import LinkedInJobSearcher
from src.linked_agent.config.constants import ApplicationStatus
from src.linked_agent.config.settings import Settings
from src.linked_agent.models.entities import Job, JobApplication, ResumeProfile
from src.linked_agent.models.rules import (
    AuthenticityExclusionSpecification,
    CompanyExclusionSpecification,
    ConsultancyScamSpecification,
    DescriptionExclusionSpecification,
    JobSpecification,
    LinkedInScamSpecification,
    TitleExclusionSpecification,
)
from src.linked_agent.utils.exceptions import LLMAPIError, LLMQuotaExceededError
from src.linked_agent.utils.notification import send_notification
from src.linked_agent.utils.telemetry import MetricsTracker
from src.linked_agent.utils.email_sender import _build_html_report, send_external_jobs_email
from src.linked_agent.bot.interfaces import (
    IBrowserEngine,
    IBrowserInteractions,
    IJobMatcher,
    ILLMProvider,
    IQuestionAnswerer,
    IRepository,
    IResumeParser,
)
from src.linked_agent.bot.factory import LinkedInDependencyFactory
from src.linked_agent.utils.helpers import TimeUtility
from src.linked_agent.utils.logger import (
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


class LinkedInAgent:
    """
    The main orchestration engine for LinkedIn job automation.

    Usage:
        factory = LinkedInDependencyFactory(settings)
        agent = LinkedInAgent(factory)
        await agent.run()
    """

    _factory: LinkedInDependencyFactory | None
    _settings: Settings
    _repo: IRepository
    _engine: IBrowserEngine
    _interactions: IBrowserInteractions
    _llm: ILLMProvider
    _resume_parser: IResumeParser
    _login_handler: LinkedInLoginHandler
    _job_searcher: LinkedInJobSearcher
    _job_matcher: IJobMatcher
    _question_answerer_factory: Callable[[ResumeProfile], IQuestionAnswerer]
    _job_applier_factory: Callable[[IQuestionAnswerer], LinkedInJobApplier]
    _resume_profile: ResumeProfile | None

    def __init__(
        self,
        factory: LinkedInDependencyFactory | None = None,
        *,
        settings: Settings | None = None,
        repository: IRepository | None = None,
        browser_engine: IBrowserEngine | None = None,
        browser_interactions: IBrowserInteractions | None = None,
        llm_provider: ILLMProvider | None = None,
        resume_parser: IResumeParser | None = None,
        login_handler: LinkedInLoginHandler | None = None,
        job_searcher: LinkedInJobSearcher | None = None,
        job_matcher: IJobMatcher | None = None,
        question_answerer_factory: Callable[[ResumeProfile], IQuestionAnswerer] | None = None,
        job_applier_factory: Callable[[IQuestionAnswerer], LinkedInJobApplier] | None = None,
    ) -> None:
        self._factory = factory

        _settings = settings or (factory.get_settings() if factory else None)
        if not _settings:
            raise ValueError("Either factory or settings must be provided.")
        self._settings = _settings

        _repo = repository or (factory.get_repository() if factory else None)
        if not _repo:
            raise ValueError("Repository is required.")
        self._repo = _repo

        _engine = browser_engine or (factory.get_browser_engine() if factory else None)
        if not _engine:
            raise ValueError("Browser engine is required.")
        self._engine = _engine

        _interactions = browser_interactions or (factory.get_browser_interactions() if factory else None)
        if not _interactions:
            raise ValueError("Browser interactions are required.")
        self._interactions = _interactions

        _llm = llm_provider or (factory.get_llm_provider() if factory else None)
        if not _llm:
            raise ValueError("LLM provider is required.")
        self._llm = _llm

        _resume_parser = resume_parser or (factory.create_resume_parser() if factory else None)
        if not _resume_parser:
            raise ValueError("Resume parser is required.")
        self._resume_parser = _resume_parser

        _login_handler = login_handler or (factory.create_login_handler() if factory else None)
        if not _login_handler:
            raise ValueError("Login handler is required.")
        self._login_handler = _login_handler

        _job_searcher = job_searcher or (factory.create_job_searcher() if factory else None)
        if not _job_searcher:
            raise ValueError("Job searcher is required.")
        self._job_searcher = _job_searcher

        _job_matcher = job_matcher or (factory.create_job_matcher() if factory else None)
        if not _job_matcher:
            raise ValueError("Job matcher is required.")
        self._job_matcher = _job_matcher

        if question_answerer_factory:
            self._question_answerer_factory = question_answerer_factory
        elif factory:
            self._question_answerer_factory = lambda profile: factory.create_question_answerer(profile)
        else:
            raise ValueError("Question answerer factory is required.")

        if job_applier_factory:
            self._job_applier_factory = job_applier_factory
        elif factory:
            self._job_applier_factory = lambda qa: factory.create_job_applier(qa)
        else:
            raise ValueError("Job applier factory is required.")

        self._resume_profile = None
        self._run_log_id: int | None = None
        self._interrupted = False
        self._external_jobs: list[tuple[Job, str | None, str, str]] = []
        self._last_flush_count = 0

        # Counters
        self._jobs_found = 0
        self._jobs_applied = 0
        self._jobs_skipped = 0
        self._jobs_failed = 0
        self._daily_applied = 0

        # Job Exclusions Specification
        self._exclusion_spec: JobSpecification | None = None

    async def run(self, dry_run: bool = False) -> None:
        """Execute the full LinkedIn agent loop."""
        if dry_run:
            self._settings.application.dry_run = True

        self._print_banner()
        setup_logging(
            level=self._settings.logging.level,
            log_to_file=self._settings.logging.log_to_file,
            log_dir=str(self._settings.project_root / self._settings.logging.log_dir),
        )
        self._settings.ensure_dirs()
        self._register_signal_handlers()

        try:
            log_info("Starting LinkedIn agent run...")
            if self._repo:
                await self._repo.initialize()
                self._run_log_id = await self._repo.create_run_log(
                    search_keywords=self._settings.search.keywords
                )

            await self._parse_resume()
            if not self._resume_profile:
                log_error("Cannot proceed without a parsed resume profile.")
                return

            await self._engine.launch()

            login_success = await self._login_handler.login()
            if not login_success:
                log_error("LinkedIn login failed. Cannot proceed.")
                return

            jobs = await self._job_searcher.search_all()
            self._jobs_found = len(jobs)

            if not jobs:
                log_warning("No LinkedIn jobs found matching your search criteria.")
                return

            log_success(f"Found {len(jobs)} candidate LinkedIn jobs. Starting evaluation...")

            # Early scam/consultancy pass — only possible without full description.
            # Catches obvious agency companies via company name / title signals alone.
            # A deeper re-check runs after description is fetched (inside _is_excluded).
            if self._settings.exclusions.enable_scam_filter:
                scam_spec = ConsultancyScamSpecification()
                clean_jobs: list[Job] = []
                scam_jobs: list[Job] = []
                for job in jobs:
                    if scam_spec.is_satisfied_by(job):
                        scam_jobs.append(job)
                    else:
                        clean_jobs.append(job)

                if scam_jobs:
                    log_warning(
                        f"Early scam filter removed {len(scam_jobs)}/{len(jobs)} jobs "
                        f"({len(clean_jobs)} remain for processing)"
                    )
                    for j in scam_jobs:
                        log_info(f"  Removed (scam/consultancy): {j.title} @ {j.company}")

                    if (
                        self._settings.application.email_notifications_enabled
                        and self._settings.application.notify_on_scam
                    ):
                        from src.linked_agent.utils.notification import send_notification

                        flagged_list = "\n".join(
                            f"  - {j.title} @ {j.company}" for j in scam_jobs
                        )
                        await send_notification(
                            self._settings,
                            "scam.detected",
                            f"Scam Filter: {len(scam_jobs)} suspicious jobs removed",
                            f"<p>The following jobs were removed by scam filter:</p><pre>{flagged_list}</pre>",
                        )
                else:
                    log_success("Early scam filter passed — no obvious consultancies detected.")

                jobs = clean_jobs
            else:
                log_info("Early scam filter skipped (enable_scam_filter: false in config).")

            log_success(f"{len(jobs)} candidate jobs ready for evaluation.")

            # Build exclusion specs
            exclusions = self._settings.exclusions
            base_exclusion_spec: JobSpecification = (
                CompanyExclusionSpecification(exclusions.companies)
                | TitleExclusionSpecification(exclusions.title_keywords)
                | DescriptionExclusionSpecification(exclusions.description_keywords)
                | AuthenticityExclusionSpecification(
                    exclusions.fake_company_blocklist, exclusions.max_openings_without_logo
                )
            )

            if exclusions.enable_scam_filter:
                self._exclusion_spec = base_exclusion_spec | LinkedInScamSpecification()
            else:
                self._exclusion_spec = base_exclusion_spec

            matcher = self._job_matcher
            qa = self._question_answerer_factory(self._resume_profile)
            applier = self._job_applier_factory(qa)

            resume_text = " ".join(
                filter(None, self._resume_profile.skills
                + [self._resume_profile.current_title]
                + [self._resume_profile.summary])
            )

            doc_frequencies: dict[str, int] = {}
            total_documents = 0
            if self._repo:
                try:
                    from collections import Counter
                    all_descriptions = await self._repo.get_all_job_descriptions()
                    total_documents = len(all_descriptions)
                    df_counter: Counter[str] = Counter()
                    for desc in all_descriptions:
                        if desc:
                            words = set(re.findall(r"\b[a-z0-9]+\b", desc.lower()))
                            df_counter.update(words)
                    doc_frequencies = dict(df_counter)
                except Exception as e:
                    logger.warning(f"Failed to build TF-IDF corpus: {e}")

            vector_filter = LinkedInVectorSimilarityFilter(
                resume_text, doc_frequencies=doc_frequencies, total_documents=total_documents
            )

            await self._process_jobs(jobs, matcher, applier, vector_filter)

        except KeyboardInterrupt:
            log_warning("LinkedIn agent interrupted by user")
            self._interrupted = True
        except Exception as e:
            if self._interrupted:
                log_warning("Agent run interrupted. Shutting down gracefully.")
            else:
                log_error(f"LinkedIn agent error: {e}")
                logger.exception("Agent fatal error")
        finally:
            await self._cleanup()

    async def _parse_resume(self) -> None:
        """Parse the resume PDF and cache the structured profile."""
        resume_path = self._settings.resume.path
        if not resume_path:
            log_error("Resume path not configured")
            return

        path = Path(resume_path)
        if not path.is_absolute():
            path = self._settings.project_root / path

        if not path.exists():
            log_error(f"Resume file not found: {path}")
            return

        self._resume_profile = await self._resume_parser.parse(str(path))

        if self._resume_profile:
            console.print(
                Panel(
                    f"[bold]{self._resume_profile.name or 'Unknown'}[/bold]\n"
                    f"Skills: {', '.join(self._resume_profile.skills[:10])}...\n"
                    f"Experience: {self._resume_profile.total_experience_years} years\n"
                    f"Title: {self._resume_profile.current_title or 'N/A'}",
                    title="Resume Profile",
                    border_style="cyan",
                )
            )

    async def _process_jobs(
        self,
        jobs: list[Job],
        matcher: IJobMatcher,
        applier: LinkedInJobApplier,
        vector_filter: LinkedInVectorSimilarityFilter,
    ) -> None:
        """Process jobs using priority queue, pre-filter, AI match, and apply."""
        log_info("Building priority queue for optimal processing order...")

        assert self._resume_profile is not None
        resume_profile = self._resume_profile
        job_queue: list[tuple[float, int, Job]] = []

        for idx, job in enumerate(jobs):
            if self._is_excluded(job):
                log_info(f"Skipping excluded: {job.title} @ {job.company}")
                self._jobs_skipped += 1
                continue

            if not self._passes_required_title(job):
                log_info(f"Skipping (title missing required keyword): {job.title} @ {job.company}")
                self._jobs_skipped += 1
                continue

            if self._settings.search.enable_heuristics:
                text_to_score = f"{job.title} {job.company} {job.skills}"
                score = vector_filter.get_similarity_score(text_to_score)

                title_lower = (job.title or "").lower()
                title_words = set(re.findall(r"\b[a-z0-9]+\b", title_lower))

                search_kw_words = set()
                for kw in self._settings.search.keywords:
                    search_kw_words.update(re.findall(r"\b[a-z0-9]+\b", kw.lower()))

                if title_words & search_kw_words:
                    score += 0.15

                tech_skills_words = set()
                for skill in resume_profile.technical_skills[:10]:
                    tech_skills_words.update(re.findall(r"\b[a-z0-9]+\b", skill.lower()))

                if title_words & tech_skills_words:
                    score += 0.10

                posted = str(job.posted_date).lower()
                if "just now" in posted or "hour" in posted or "today" in posted:
                    score += 0.10
                elif "1 day" in posted or "2 days" in posted:
                    score += 0.05
            else:
                score = 0.0

            heapq.heappush(job_queue, (-score, idx, job))

        total_jobs = len(job_queue)
        self._daily_applied = await self._repo.get_today_application_count() if self._repo else 0
        processed_count = 0

        # Early exit if daily cap already reached
        remaining = self._settings.application.daily_cap - self._daily_applied
        if remaining <= 0:
            log_warning(f"Daily cap already reached ({self._daily_applied}/{self._settings.application.daily_cap}). Skipping processing.")
            return

        log_info(f"Daily cap: {self._daily_applied}/{self._settings.application.daily_cap} used. {remaining} remaining.")

        while job_queue:
            if self._interrupted:
                break

            neg_score, idx, job = heapq.heappop(job_queue)
            initial_score = -neg_score

            remaining = self._settings.application.daily_cap - self._daily_applied
            if remaining <= 0:
                log_warning(f"Daily cap reached ({self._settings.application.daily_cap}). Stopping.")
                break

            processed_count += 1
            log_step(
                processed_count, total_jobs,
                f"{job.title} @ {job.company} (Score: {initial_score:.2f})",
            )

            # Periodic progress report every 20 jobs
            if processed_count % 20 == 0:
                success_rate = (self._jobs_applied / max(processed_count, 1)) * 100
                log_info(
                    f"PROGRESS [{processed_count}/{total_jobs}] — "
                    f"Applied: {self._jobs_applied} | Skipped: {self._jobs_skipped} | "
                    f"Failed: {self._jobs_failed} | Success rate: {success_rate:.1f}% | "
                    f"Daily: {self._daily_applied}/{self._settings.application.daily_cap}"
                )
                # Save local HTML report every 20 jobs (free backup, no email sent)
                try:
                    self._save_local_report()
                except Exception as exc:
                    logger.warning(f"Local report save error: {exc}")

            # Dedup
            if self._repo:
                if self._repo.is_already_applied(job.linkedin_job_id):
                    log_info("Skipping duplicate (LinkedIn ID)")
                    self._jobs_skipped += 1
                    continue
                if self._repo.is_already_applied_composite(job.title, job.company):
                    log_info("Skipping duplicate (title+company)")
                    self._jobs_skipped += 1
                    continue

            if self._is_excluded(job):
                log_info(f"Skipping excluded: {job.title} @ {job.company}")
                self._jobs_skipped += 1
                continue

            if not self._passes_required_title(job):
                log_info(f"Skipping (title missing required keyword): {job.title} @ {job.company}")
                self._jobs_skipped += 1
                continue

            # Browser health check
            if not self._engine.is_alive():
                log_warning("Browser disconnected! Attempting recovery...")
                with contextlib.suppress(PlaywrightTimeoutError, PlaywrightError):
                    await self._engine.close()
                try:
                    await self._engine.launch()
                    login_success = await self._login_handler.login()
                    if not login_success:
                        log_error("Re-login failed after browser restart. Stopping.")
                        break
                    log_success("Browser recovered successfully.")
                except Exception as e:
                    log_error(f"Browser recovery failed: {e}. Stopping.")
                    break

            # Get full description — navigate to sidebar using currentJobId URL
            sidebar_already_applied = False
            if not job.description:
                sidebar_opened = await self._navigate_to_job_sidebar(job)

                if sidebar_opened:
                    sidebar_details = await self._job_searcher._search_page.extract_sidebar_details()
                    job.description = sidebar_details.get("description", "")
                    if sidebar_details.get("skills"):
                        job.skills = sidebar_details["skills"]
                    if sidebar_details.get("location"):
                        job.location = sidebar_details["location"]
                    job.easy_apply = sidebar_details.get("easy_apply", job.easy_apply)
                    sidebar_already_applied = sidebar_details.get("already_applied", False)
                else:
                    logger.warning(f"Could not open sidebar for description: {job.title} @ {job.company}")

                await self._interactions.action_delay()

            # Re-evaluate exclusions with full description
            if self._is_excluded(job):
                log_info(f"Skipping after description fetch: {job.title} @ {job.company}")
                self._jobs_skipped += 1
                if (
                    self._settings.exclusions.enable_scam_filter
                    and self._settings.application.email_notifications_enabled
                    and self._settings.application.notify_on_scam
                ):
                    await send_notification(
                        self._settings,
                        "scam.detected",
                        f"Scam/consultancy job caught after description fetch: {job.title} @ {job.company}",
                        f"<p>Job: {job.title} @ {job.company}<br>URL: {job.url}</p>",
                    )
                continue

            if not self._passes_required_title(job):
                log_info(f"Skipping (title missing required keyword): {job.title} @ {job.company}")
                self._jobs_skipped += 1
                continue

            # Similarity pre-filter
            full_text = f"{job.title} {job.company} {job.skills} {job.description}"
            full_sim_score = vector_filter.get_similarity_score(full_text)
            if full_sim_score < 0.04:
                log_info(f"Skipping: similarity ({full_sim_score:.3f}) below threshold")
                self._jobs_skipped += 1
                continue

            # AI matching
            if not self._settings.ai.enable_matching:
                match_result = JobApplication(
                    match_score=100.0, should_apply=True,
                    match_reasoning="AI matching bypassed",
                    matching_skills="Bypassed", missing_skills="Bypassed",
                )
            else:
                try:
                    match_result = await matcher.match(resume_profile, job)
                except (LLMQuotaExceededError, LLMAPIError) as e:
                    if self._settings.ai.fallback_model:
                        fallback_model = self._settings.ai.fallback_model
                        log_warning(f"Primary model failed. Switching to {fallback_model}...")
                        if hasattr(self._llm, "set_model"):
                            self._llm.set_model(fallback_model)
                        self._settings.ai.model = fallback_model
                        self._settings.ai.fallback_model = None
                        try:
                            match_result = await matcher.match(resume_profile, job)
                        except (LLMQuotaExceededError, LLMAPIError) as e2:
                            log_error(f"Fallback model also failed: {e2}")
                            if isinstance(e2, LLMQuotaExceededError) and e2.is_daily_quota and self._settings.ai.abort_on_quota:
                                self._interrupted = True
                                break
                            # Both models exhausted — disable AI matching for rest of run
                            log_warning("Both AI models exhausted — falling back to local matching")
                            self._settings.ai.enable_matching = False
                            match_result = matcher._local_match(resume_profile, job)
                        except Exception:
                            log_error("Fallback model failed unexpectedly — falling back to local matching")
                            self._settings.ai.enable_matching = False
                            match_result = matcher._local_match(resume_profile, job)
                    else:
                        if isinstance(e, LLMQuotaExceededError) and e.is_daily_quota and self._settings.ai.abort_on_quota:
                            self._interrupted = True
                            break
                        # AI model exhausted — fall back to local matching for rest of run
                        log_warning("AI model exhausted — falling back to local matching")
                        self._settings.ai.enable_matching = False
                        match_result = matcher._local_match(resume_profile, job)
                except Exception as e:
                    logger.error(f"AI Match failed: {e}")
                    self._jobs_failed += 1
                    continue

            # Save job
            db_job = None
            if self._repo:
                db_job = await self._repo.save_job(
                    linkedin_job_id=job.linkedin_job_id,
                    title=job.title,
                    company=job.company,
                    url=job.url,
                    location=job.location,
                    experience=job.experience,
                    salary=job.salary,
                    description=job.description,
                    skills=job.skills,
                    posted_date=job.posted_date,
                    job_type=job.job_type,
                    work_type=job.work_type,
                    applicant_count=job.applicant_count,
                    easy_apply=job.easy_apply,
                )

            match_score = match_result.match_score
            threshold = self._settings.application.match_score_threshold

            # Enforce the match score threshold configured via the UI/settings.
            if match_score < threshold:
                log_info(
                    f"Skipping: {job.title} @ {job.company} "
                    f"(score: {match_score:.1f}) below threshold ({threshold}%)"
                )
                if self._repo and db_job and db_job.id is not None:
                    await self._repo.save_application(
                        job_id=db_job.id, match_score=match_score,
                        status=ApplicationStatus.SKIPPED_LOW_SCORE,
                        match_reasoning=match_result.match_reasoning,
                        matching_skills=match_result.matching_skills,
                        missing_skills=match_result.missing_skills,
                    )
                self._jobs_skipped += 1
                continue

            log_info(
                f"Applying: {job.title} @ {job.company} "
                f"(AI score: {match_score:.1f}, threshold: {threshold}%)"
            )

            if self._settings.application.dry_run:
                log_info(f"DRY RUN — would apply (score: {match_score})")
                if self._repo and db_job and db_job.id is not None:
                    await self._repo.save_application(
                        job_id=db_job.id, match_score=match_score,
                        status=ApplicationStatus.SKIPPED_DRY_RUN,
                        match_reasoning=match_result.match_reasoning,
                        matching_skills=match_result.matching_skills,
                        missing_skills=match_result.missing_skills,
                    )
                self._jobs_skipped += 1
                continue

            # Ensure sidebar is open for this job using reliable currentJobId navigation
            sidebar_opened = await self._navigate_to_job_sidebar(job)
            if not sidebar_opened:
                logger.warning(f"Could not open sidebar for apply: {job.title} @ {job.company}")
                self._jobs_skipped += 1
                continue

            # Apply from sidebar
            apply_result = await applier.apply_to_job(job, sidebar_already_applied=sidebar_already_applied)
            status = apply_result.get("status", ApplicationStatus.FAILED)
            error_msg = apply_result.get("error_message", "")

            if self._repo and db_job and db_job.id is not None:
                await self._repo.save_application(
                    job_id=db_job.id, match_score=match_score,
                    status=status, match_reasoning=match_result.match_reasoning,
                    matching_skills=match_result.matching_skills,
                    missing_skills=match_result.missing_skills,
                    error_message=error_msg,
                )

            if status == ApplicationStatus.APPLIED:
                self._jobs_applied += 1
                self._daily_applied += 1
                await TimeUtility.random_delay(
                    self._settings.application.delay_between_applies_min,
                    self._settings.application.delay_between_applies_max,
                )
            else:
                # Collect ALL non-applied jobs for email report
                ext_url = apply_result.get("external_url")
                self._external_jobs.append((job, ext_url, status, error_msg))
                if status.startswith("skipped"):
                    log_info(f"Job application skipped: {job.title} @ {job.company} — Status: {status}")
                    self._jobs_skipped += 1
                else:
                    log_error(f"Job application failed: {job.title} @ {job.company} — Error: {error_msg}")
                    self._jobs_failed += 1

            # Close sidebar after processing each job
            try:
                await self._job_searcher._search_page.close_sidebar()
            except Exception:
                pass

    def _save_local_report(self) -> None:
        """Save a local HTML report of accumulated external/failed jobs.
        Only sends email in _cleanup() — this is a free backup."""
        if (
            not getattr(self._settings.application, "collect_external_jobs", False)
            or not self._external_jobs
        ):
            return
        if len(self._external_jobs) <= self._last_flush_count:
            return
        unsent = self._external_jobs[self._last_flush_count:]
        if not unsent:
            return

        report_dir = self._settings.project_root / "data" / "linkedin" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        local_path = report_dir / f"external_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        all_data = list(self._external_jobs)

        try:
            html = _build_html_report(all_data, self._settings)
            local_path.write_text(html, encoding="utf-8")
            logger.info(f"Saved local report to {local_path}")
            self._last_flush_count = len(self._external_jobs)
        except Exception as e:
            logger.warning(f"Failed to save local report: {e}")

    async def _navigate_to_job_sidebar(self, job: Job) -> bool:
        """Navigate to the job's sidebar using the reliable currentJobId URL pattern.

        Instead of relying on card_index (which breaks because LinkedIn
        virtualizes its DOM — only ~9-10 cards visible at a time), this
        constructs a URL with currentJobId={linkedin_job_id} which directly
        opens the correct job's sidebar panel.

        Strategy:
        1. Build search URL with currentJobId parameter → opens sidebar directly
        2. If search_url unavailable, navigate to /jobs/view/{id} → detail page
        3. Wait for the Apply button area to render (React lazy loading)
        """
        page = self._engine.page
        job_id = job.linkedin_job_id

        if not job_id:
            logger.warning(f"No linkedin_job_id for {job.title} @ {job.company}")
            return False

        # Strategy 1: Append currentJobId to the search URL
        target_url = None
        if job.search_url:
            separator = "&" if "?" in job.search_url else "?"
            # Remove any existing currentJobId from the search_url
            base_url = re.sub(r'[&?]currentJobId=\d+', '', job.search_url)
            target_url = f"{base_url}{separator}currentJobId={job_id}"
        else:
            # Fallback: construct a minimal search URL with just currentJobId
            target_url = f"https://www.linkedin.com/jobs/search/?currentJobId={job_id}"

        for attempt in range(2):
            try:
                logger.debug(f"Navigating to sidebar (attempt {attempt+1}): {target_url[:120]}")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                await asyncio.sleep(2)

                # Verify we're on a search page with the job sidebar open
                current_url = page.url
                if "currentJobId" in current_url or "/jobs/view/" in current_url:
                    # Wait for Apply button area to render — using textContent
                    # matching to catch buttons where text is in nested elements
                    try:
                        await page.wait_for_selector(
                            'button:has-text("Apply"):not(:has-text("Show"):has-text("Filter")), '
                            'button[aria-label*="Apply" i], '
                            'button[aria-label*="already applied" i], '
                            'span:text-is("Applied")',
                            timeout=10000, state='visible'
                        )
                    except PlaywrightTimeoutError:
                        logger.debug("Apply button area not visible yet — continuing anyway")

                    return True

                # If redirected away (e.g., to login), retry once
                if "/login" in current_url or "signup" in current_url:
                    logger.warning("Session expired during sidebar navigation — cannot proceed")
                    return False

                logger.warning(f"Sidebar navigation redirected: {current_url[:100]}")

            except Exception as e:
                logger.warning(f"Sidebar navigation attempt {attempt+1} failed: {e}")
                if attempt == 0:
                    await asyncio.sleep(2)

        # Strategy 2: Direct job page as last resort
        if job.url:
            try:
                logger.info(f"Falling back to direct job URL: {job.url[:80]}")
                await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                await asyncio.sleep(2)
                try:
                    await page.wait_for_selector(
                        'button[aria-label*="Apply" i]',
                        timeout=8000, state='visible'
                    )
                except PlaywrightTimeoutError:
                    pass
                return True
            except Exception as e:
                logger.warning(f"Direct job URL navigation failed: {e}")

        return False

    def _is_excluded(self, job: Job) -> bool:
        if not self._exclusion_spec:
            return False
        return self._exclusion_spec.is_satisfied_by(job)

    def _passes_required_title(self, job: Job) -> bool:
        """Hard gate: if required_title_keywords is set, the job title must contain
        at least one of them (word-boundary matched). Used to restrict the agent
        to a specific job family, e.g. only Java developer roles."""
        required = getattr(self._settings.search, "required_title_keywords", [])
        if not required:
            return True
        title_lower = (job.title or "").lower()
        for kw in required:
            pattern = rf"\b{re.escape(kw.lower())}\b"
            if re.search(pattern, title_lower):
                return True
        return False

    async def _cleanup(self) -> None:
        # Send external jobs email if needed
        if (
            getattr(self._settings.application, "collect_external_jobs", False)
            and self._external_jobs
        ):
            try:
                await asyncio.to_thread(
                    send_external_jobs_email, self._external_jobs, self._settings
                )
            except Exception as e:
                logger.error(f"Failed to send external jobs email: {e}")

        if self._repo and self._run_log_id:
            status = "interrupted" if self._interrupted else "completed"
            await self._repo.update_run_log(
                run_log_id=self._run_log_id,
                jobs_found=self._jobs_found,
                jobs_applied=self._jobs_applied,
                jobs_skipped=self._jobs_skipped,
                jobs_failed=self._jobs_failed,
                status=status,
            )

        # Track metrics
        metrics = MetricsTracker(str(self._settings.project_root / self._settings.logging.log_dir))
        metrics.record_run(self._jobs_applied, self._jobs_failed)

        self._print_summary()

        if self._engine:
            try:
                await self._engine.close()
            except (PlaywrightTimeoutError, PlaywrightError):
                pass

    def _print_banner(self) -> None:
        console.print(
            Panel(
                "[bold cyan]LinkedIn Auto-Apply Agent[/bold cyan]\n\n"
                f"  Keywords: {', '.join(self._settings.search.keywords)}\n"
                f"  Locations: {', '.join(self._settings.search.locations)}\n"
                f"  Daily Cap: {self._settings.application.daily_cap}\n"
                f"  Match Threshold: {self._settings.application.match_score_threshold}%\n"
                f"  AI Matching: {'Enabled' if self._settings.ai.enable_matching else 'Disabled'}\n"
                f"  Easy Apply Only: {'Yes' if self._settings.application.easy_apply_only else 'No'}\n"
                f"  Dry Run: {'Yes' if self._settings.application.dry_run else 'No'}\n"
                f"  AI Model: {self._settings.ai.model}\n"
                f"  Freshness: {self._settings.search.freshness}\n"
                f"  Max Pages: {self._settings.search.max_pages}\n"
                f"  Apply Delay: {self._settings.application.delay_between_applies_min}-{self._settings.application.delay_between_applies_max}s",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    def _print_summary(self) -> None:
        total_processed = self._jobs_applied + self._jobs_skipped + self._jobs_failed
        success_rate = (self._jobs_applied / max(total_processed, 1)) * 100

        table = Table(
            title="Run Summary",
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
        table.add_row("Success Rate", f"[bold]{success_rate:.1f}%[/bold]")
        table.add_row("Daily Cap Used", f"{self._daily_applied}/{self._settings.application.daily_cap}")
        console.print()
        console.print(table)
        console.print()

    def _register_signal_handlers(self) -> None:
        def handle_signal(signum, frame):
            log_warning("Received shutdown signal. Cleaning up...")
            self._interrupted = True

        if sys.platform != "win32":
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        else:
            signal.signal(signal.SIGINT, handle_signal)

    async def parse_resume_only(self, resume_path: str) -> ResumeProfile | None:
        profile = await self._resume_parser.parse(resume_path)
        if profile:
            profile_dict = dataclasses.asdict(profile)
            console.print_json(json.dumps(profile_dict, indent=2, ensure_ascii=False))
        return profile
