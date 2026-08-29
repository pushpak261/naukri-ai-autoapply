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
import re
import signal
import sys
from collections.abc import Callable
from pathlib import Path

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from rich.panel import Panel
from rich.table import Table

from src.naukri_agent.utils.similarity import VectorSimilarityFilter
from src.naukri_agent.fake_job_detection import FakeJobDetectionPipeline
from src.naukri_agent.browser.apply import JobApplier
from src.naukri_agent.browser.login import LoginHandler
from src.naukri_agent.browser.profile import ProfileRefresher
from src.naukri_agent.browser.search import JobSearcher
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, JobApplication, ResumeProfile
from src.naukri_agent.bot.interfaces import (
    IBrowserEngine,
    IBrowserInteractions,
    IJobMatcher,
    ILLMProvider,
    IQuestionAnswerer,
    IRepository,
    IResumeParser,
)
from src.naukri_agent.bot.factory import DependencyFactory
from src.naukri_agent.utils.helpers import TimeUtility
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
        self._external_jobs: list[tuple[Job, str | None]] = []
        self._pipeline: FakeJobDetectionPipeline | None = None

        # Counters
        self._jobs_found = 0
        self._jobs_applied = 0
        self._jobs_skipped = 0
        self._jobs_failed = 0
        self._daily_applied = 0

    async def run(self, dry_run: bool = False) -> None:
        """
        Execute the full agent loop.

        Args:
            dry_run: If True, score jobs but don't actually apply.
        """
        if dry_run:
            self._settings.application.dry_run = True

        # Reset any prior external-block state at the start of a run.
        from api.agent_runtime import clear_agent_blocked

        clear_agent_blocked()

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

        try:
            # Step 1: Initialize run log
            log_info("Starting agent run...")
            if self._repo:
                await self._repo.initialize()
                self._run_log_id = await self._repo.create_run_log(
                    search_keywords=self._settings.search.keywords
                )

            # Step 2: Parse resume
            await self._parse_resume()
            if not self._resume_profile:
                log_error("Cannot proceed without a parsed resume profile.")
                return

            # Step 3: Launch browser & login
            await self._engine.launch()

            login_handler = self._login_handler
            if not login_handler:
                raise RuntimeError("LoginHandler not configured.")
            login_success = await login_handler.login()
            if not login_success:
                from api.agent_runtime import mark_agent_blocked
                from src.naukri_agent.bot.block_detector import classify_block

                last_err = getattr(login_handler, "last_error", "") or ""
                block = classify_block(last_err)
                if block:
                    await mark_agent_blocked(self._settings, block, None)
                log_error("Login failed. Cannot proceed.")
                return

            # Step 4: Search for jobs
            searcher = self._job_searcher
            if not searcher:
                raise RuntimeError("JobSearcher not configured.")
            jobs = await searcher.search_all(should_stop=lambda: self._interrupted)
            self._jobs_found = max(self._jobs_found, len(jobs))

            if self._interrupted:
                log_warning(
                    f"Run interrupted during search — {self._jobs_found} jobs were found "
                    f"before stopping. Skipping job evaluation."
                )
                return

            if not jobs:
                log_warning("No jobs found matching your search criteria.")
                return

            log_success(f"Found {len(jobs)} candidate jobs. Starting evaluation...")

            # Initialize the fake job detection pipeline (Stages 1-5)
            self._pipeline = FakeJobDetectionPipeline(self._settings.exclusions)

            # Stage 1: Early scam pass — uses only title/company (no description needed)
            clean_jobs, scam_jobs = self._pipeline.early_scam_filter(jobs)
            self._jobs_skipped += len(scam_jobs)
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
                    from src.naukri_agent.utils.notification import send_notification

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
            log_success(f"{len(jobs)} candidate jobs ready for evaluation.")

            # Stages 2 + 3 + 5: Build composed exclusion specification
            self._pipeline.build_exclusion_spec()
            if self._pipeline.is_scam_filter_enabled:
                log_info("Scam / consultancy filter is ENABLED")
            else:
                log_info("Scam / consultancy filter is DISABLED (enable_scam_filter: false)")

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
            # Compute document frequency for TF-IDF from DB corpus
            doc_frequencies = {}
            total_documents = 0
            if self._repo:
                try:
                    import re
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
                    logger.warning(f"Failed to build TF-IDF corpus from DB: {e}")

            vector_filter = VectorSimilarityFilter(
                resume_text, doc_frequencies=doc_frequencies, total_documents=total_documents
            )

            # Step 6: Process each job using Priority Queue Max-Heap
            await self._process_jobs(jobs, matcher, applier, searcher, vector_filter)

        except KeyboardInterrupt:
            log_warning("Agent interrupted by user (Ctrl+C)")
            self._interrupted = True
        except Exception as e:
            if self._interrupted:
                log_warning(
                    "Agent run interrupted during browser operation. Shutting down gracefully."
                )
            else:
                log_error(f"Agent error: {e}")
                logger.exception("Agent fatal error")
        finally:
            await self._cleanup()

    async def _parse_resume(self) -> None:
        """Parse the resume PDF and cache the structured profile."""
        # First check if there's an uploaded resume file path in resume_profile.json
        uploaded_file_path: str | None = None
        profile_json_path = self._settings.project_root / "resume_profile.json"
        if profile_json_path.exists():
            try:
                import json as _json

                existing = _json.loads(profile_json_path.read_text(encoding="utf-8"))
                uploaded = existing.get("uploaded_file_path")
                if uploaded and Path(uploaded).exists():
                    uploaded_file_path = uploaded
                    log_info(f"Using uploaded resume file: {uploaded}")
            except Exception:
                pass

        if uploaded_file_path:
            path = Path(uploaded_file_path)
        else:
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
        if self._settings.search.enable_heuristics:
            log_info("Building Max-Heap Priority Queue for optimal processing order...")
        else:
            log_info("Processing jobs sequentially (heuristics disabled)...")

        assert self._resume_profile is not None, (
            "_process_jobs() requires a parsed resume profile; run() must "
            "check and return early before calling this."
        )
        resume_profile = self._resume_profile
        job_queue: list[tuple[float, int, Job]] = []
        for idx, job in enumerate(jobs):
            # Compute heuristic score first for dynamic exclusion gating
            heuristic_score = 0.0
            if self._settings.search.enable_heuristics:
                text_to_score = f"{job.title} {job.company} {job.skills}"
                heuristic_score = vector_filter.get_similarity_score(text_to_score)
            # Apply exclusion filters at scrape time so only required jobs enter the queue.
            # Passing heuristic_score makes title keyword exclusion dynamic —
            # jobs with reasonable similarity to the resume bypass title blocks.
            if self._pipeline and self._pipeline.is_excluded(job, heuristic_score):
                log_info(f"Skipping job at scrape time: matches exclusion keywords ({job.title} @ {job.company})")
                self._jobs_skipped += 1
                continue

            if self._settings.search.enable_heuristics:
                logger.debug(f"Heuristics ENABLED for job: {job.title} @ {job.company}")
                base_score = heuristic_score
                score = base_score
                logger.debug(f"  - Base TF-IDF score: {base_score:.3f}")

                # Recalibrate heuristics: Boost for search keywords and resume skills in title
                title_lower = (job.title or "").lower()
                title_words = set(re.findall(r"\b[a-z0-9]+\b", title_lower))

                # Word-based overlap between title and search keywords
                search_keywords = self._settings.search.keywords
                search_kw_words = set()
                for kw in search_keywords:
                    search_kw_words.update(re.findall(r"\b[a-z0-9]+\b", kw.lower()))

                if title_words & search_kw_words:
                    score += 0.15
                    logger.debug(
                        f"  - Boost (+0.15): Title matches search keywords ({title_words & search_kw_words})"
                    )

                # Word-based overlap between title and top resume technical skills
                tech_skills_words = set()
                for skill in resume_profile.technical_skills[:10]:
                    tech_skills_words.update(re.findall(r"\b[a-z0-9]+\b", skill.lower()))

                if title_words & tech_skills_words:
                    score += 0.10
                    logger.debug(
                        f"  - Boost (+0.10): Title matches technical skills ({title_words & tech_skills_words})"
                    )

                # Boost for very fresh jobs
                posted = str(job.posted_date).lower()
                if "just now" in posted or "hour" in posted or "today" in posted:
                    score += 0.10
                    logger.debug(f"  - Boost (+0.10): Very fresh job ({posted})")
                elif "1 day" in posted or "2 days" in posted:
                    score += 0.05
                    logger.debug(f"  - Boost (+0.05): Fresh job ({posted})")

                logger.debug(f"  -> Final heuristic score: {score:.3f}")

                # Skip jobs with very low heuristic scores — clearly irrelevant
                MIN_HEURISTIC_SCORE = 0.08
                if score < MIN_HEURISTIC_SCORE:
                    logger.debug(
                        f"Skipping job: heuristic score {score:.3f} below {MIN_HEURISTIC_SCORE} "
                        f"({job.title} @ {job.company})"
                    )
                    self._jobs_skipped += 1
                    continue
            else:
                logger.debug(f"Heuristics DISABLED for job: {job.title}. Defaulting score to 0.0")
                score = 0.0

            heapq.heappush(job_queue, (-score, idx, job))

        # Log the jobs currently in the Priority Queue in sorted order
        sorted_queue = sorted(job_queue)
        logger.info(
            "Jobs in Priority Queue (ordered by priority score):\n"
            + "\n".join(
                f"  - Score: {abs(score):.2f} | {job.title} @ {job.company} (ID: {job.naukri_job_id})"
                for score, idx, job in sorted_queue
            )
        )

        total_jobs = len(job_queue)
        self._daily_applied = await self._repo.get_today_application_count() if self._repo else 0
        processed_count = 0

        while job_queue:
            if self._interrupted:
                break

            self._daily_applied = await self._repo.get_today_application_count() if self._repo else self._daily_applied

            neg_score, idx, job = heapq.heappop(job_queue)
            initial_score = -neg_score

            remaining = self._settings.application.daily_cap - self._daily_applied
            if remaining <= 0:
                log_warning(
                    f"Daily application cap reached ({self._settings.application.daily_cap}). Stopping."
                )
                break

            processed_count += 1
            log_step(
                processed_count,
                total_jobs,
                f"{job.title} @ {job.company} (Heuristic: {initial_score:.2f})",
            )

            # Deduplication
            if self._repo:
                is_applied = self._repo.is_already_applied(job.naukri_job_id)
                is_applied_comp = self._repo.is_already_applied_composite(job.title, job.company)
                if is_applied is True:
                    log_info(
                        f"Skipping duplicate: already applied (Job ID {job.naukri_job_id} matches database)"
                    )
                    self._jobs_skipped += 1
                    continue
                if is_applied_comp is True:
                    log_info(
                        f"Skipping duplicate: already applied (Composite Title + Company '{job.title} @ {job.company}' matches database)"
                    )
                    self._jobs_skipped += 1
                    continue

            # Exclusion filters (dynamic: passes heuristic_score for title gating)
            if self._pipeline and self._pipeline.is_excluded(job, initial_score):
                log_info(f"Skipping job: matches exclusion keywords ({job.title} @ {job.company})")
                self._jobs_skipped += 1
                continue

            # Check browser status before interacting
            if not self._engine.is_alive():
                log_warning("Browser disconnected! Restarting browser engine...")
                with contextlib.suppress(PlaywrightTimeoutError, PlaywrightError):
                    await self._engine.close()
                await self._engine.launch()
                try:
                    login_handler = self._login_handler
                    if not login_handler:
                        raise RuntimeError("LoginHandler not configured.")
                    await login_handler.login()
                except (PlaywrightTimeoutError, PlaywrightError) as e:
                    logger.error(f"Failed to re-login after restart: {e}")

            # Get description & key skills if not already present
            if not job.description:
                details = await searcher.get_job_description(job.url)
                job.description = details.get("description", "")
                if details.get("skills"):
                    job.skills = details["skills"]
                job.openings = details.get("openings", 0)
                job.has_company_logo = details.get("has_company_logo", False)

                if not self._interactions:
                    raise RuntimeError("BrowserInteractions not configured.")
                await self._interactions.action_delay()

            # Re-check exclusion specs with now-populated description/openings/logo data.
            # DescriptionExclusionSpecification and AuthenticityExclusionSpecification
            # check 3 (no logo + high openings) can only fire after the fetch.
            if self._pipeline and self._pipeline.is_excluded(job, initial_score):
                log_info(
                    f"Skipping job: matches exclusion keywords with full data ({job.title} @ {job.company})"
                )
                self._jobs_skipped += 1
                continue

            # Stage 5: Deep scam re-check with full description data.
            # Uses ConsultancyScamSpecification with SCAM_THRESHOLD (80) and
            # all 26+ signals including genuine offsets (G2-G4). This catches
            # borderline cases that passed the lenient Stage 1 early filter.
            if self._pipeline and self._pipeline.deep_scam_check(job):
                log_info(
                    f"Skipping job: scam/consultancy detected after fetching details ({job.title} @ {job.company})"
                )
                self._jobs_skipped += 1
                if (
                    self._settings.exclusions.enable_scam_filter
                    and self._settings.application.email_notifications_enabled
                    and self._settings.application.notify_on_scam
                ):
                    from src.naukri_agent.utils.notification import send_notification

                    await send_notification(
                        self._settings,
                        "scam.detected",
                        f"Scam/consultancy job caught after description fetch: {job.title} @ {job.company}",
                        f"<p>Job: {job.title} @ {job.company}<br>URL: {job.url}</p>",
                    )
                continue

            # Pre-AI role/domain check: block non-development roles before
            # consuming an AI API call.
            if self._is_job_in_excluded_domain(job):
                log_info(
                    f"Skipping job: non-matching role/stack/domain ({job.title} @ {job.company})"
                )
                self._jobs_skipped += 1
                continue

            # Targeting gate: only Java/Spring roles within 0-2 yrs at a real
            # company are applied. Everything else is skipped here (before any
            # AI call) so we apply to ALL matching Java jobs, not a scored subset.
            target_ok, target_reason = self._passes_targeting(job)
            if not target_ok:
                log_info(
                    f"Skipping job: not in target (Java, 0-2 yrs): {target_reason} "
                    f"({job.title} @ {job.company})"
                )
                self._jobs_skipped += 1
                continue

            # Targeted Java role reached — apply directly. The Java-stack +
            # experience gate is stricter than the AI score, so we skip the
            # TF-IDF similarity pre-filter and the AI match call entirely
            # (saving tokens and guaranteeing every matching Java job is applied).
            match_result = JobApplication(
                match_score=100.0,
                should_apply=True,
                match_reasoning="Java/Spring role within 0-2 yrs target (targeting gate)",
                matching_skills="Java/Spring (targeting gate)",
                missing_skills="",
            )
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
                    openings=job.openings,
                    has_company_logo=job.has_company_logo,
                )
                assert db_job.id is not None

            match_score = match_result.match_score
            should_apply = match_result.should_apply

            # Secondary domain/stack relevance validation: override AI if job
            # clearly belongs to a non-matching tech stack or domain.
            if should_apply and self._is_job_in_excluded_domain(job):
                log_info(
                    f"Domain/stack override: skipping {job.title} @ {job.company} "
                    f"(non-matching tech stack or domain)"
                )
                should_apply = False
                match_score = min(match_score, 40.0)

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
                except (PlaywrightTimeoutError, PlaywrightError) as e:
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
                    continue

            # Pre-claim the application row BEFORE the network apply so a crash
            # between a successful Naukri apply and persistence can't cause a
            # duplicate application on the next run.
            claimed_id = None
            if self._repo and db_job:
                claimed_id = await self._repo.begin_application(
                    job_id=db_job.id,
                    match_score=match_score,
                    match_reasoning=match_result.match_reasoning,
                    matching_skills=match_result.matching_skills,
                    missing_skills=match_result.missing_skills,
                )

            # Run apply flow
            apply_result = await applier.apply_to_job(job)
            status = apply_result.get("status", ApplicationStatus.FAILED)
            error_msg = apply_result.get("error_message", "")

            # External-block playbook: if Naukri threw a captcha/OTP/IP-ban,
            # pause and notify instead of hammering the site (which worsens a ban).
            from src.naukri_agent.bot.block_detector import classify_block

            block = classify_block(error_msg) or classify_block(status)
            if block:
                from api.agent_runtime import mark_agent_blocked

                await mark_agent_blocked(self._settings, block, job)
                if self._repo and db_job and claimed_id is not None:
                    await self._repo.finalize_application(
                        app_id=claimed_id,
                        status="failed",
                        error_message=f"External block ({block}): {error_msg}",
                    )
                self._jobs_failed += 1
                break

            if self._repo and db_job:
                if claimed_id is not None:
                    await self._repo.finalize_application(
                        app_id=claimed_id,
                        status=status,
                        error_message=error_msg,
                        match_reasoning=match_result.match_reasoning,
                        matching_skills=match_result.matching_skills,
                        missing_skills=match_result.missing_skills,
                    )
                else:
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
                await TimeUtility.random_delay(
                    self._settings.application.delay_between_applies_min,
                    self._settings.application.delay_between_applies_max,
                )
            elif status.startswith("skipped"):
                if status == ApplicationStatus.SKIPPED_EXTERNAL:
                    ext_url = apply_result.get("external_url")
                    self._external_jobs.append((job, ext_url))
                elif status == ApplicationStatus.SKIPPED_SCREENING:
                    log_warning(f"Screening questions skipped: {job.title} @ {job.company}")
                    if not getattr(self._settings.application, "answer_questions_with_pdf", True):
                        # Treat it like an external job so it gets emailed to the user
                        self._external_jobs.append((job, None))
                log_info(f"Job application skipped: {job.title} @ {job.company} — Status: {status}")
                self._jobs_skipped += 1
            else:
                log_error(
                    f"Job application failed: {job.title} @ {job.company} — Error: {error_msg}"
                )
                self._jobs_failed += 1
                if getattr(self._settings.application, "collect_external_jobs", False):
                    # Add failed jobs to the email list so the user can manually check/apply
                    self._external_jobs.append((job, None))

    @staticmethod
    def _is_job_in_excluded_domain(job: Job) -> bool:
        """
        Secondary override: check if a job belongs to a fundamentally non-matching
        tech stack, role type, or domain.
        """
        from src.naukri_agent.fake_job_detection.rules import is_job_in_excluded_domain
        is_excl, _ = is_job_in_excluded_domain(job)
        return is_excl

    def _passes_targeting(self, job: Job) -> tuple[bool, str]:
        """
        Targeting gate: decide whether a job is in scope for this user.

        In scope = a Java/Spring role that requires at most the configured
        experience ceiling (0-2 yrs, matching the resume). Anything else
        (Python/.NET/non-Java, or senior roles) is out of scope.

        Returns:
            (passed, reason)
        """
        from src.naukri_agent.fake_job_detection.rules import is_java_related

        max_exp = self._settings.search.experience_max

        # 1) Experience ceiling — only junior/associate roles (0-2 yrs).
        exp_text = str(job.experience or "").lower()
        if exp_text:
            months = [
                "jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec",
            ]
            if not any(m in exp_text for m in months):
                range_match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", exp_text)
                single_match = re.search(r"(\d+)", exp_text)
                min_req = 0
                max_req = 0
                if range_match:
                    min_req = int(range_match.group(1))
                    max_req = int(range_match.group(2))
                elif single_match:
                    min_req = int(single_match.group(1))
                    max_req = min_req

                if min_req > max_exp:
                    return (
                        False,
                        f"Experience required ({min_req} Yrs) exceeds {max_exp} Yrs target",
                    )
                # Skip clearly senior ranges even if the lower bound is within range.
                if min_req >= 3 and max_req >= 4:
                    return (
                        False,
                        f"Senior role ({min_req}-{max_req} Yrs) exceeds {max_exp} Yrs target",
                    )

        # 2) Java/Spring stack requirement.
        ok, reason = is_java_related(job)
        if not ok:
            return False, reason

        return True, "Java/Spring role within 0-2 yrs at a real company"

    async def _cleanup(self) -> None:
        """Save state, update run log, print summary, and close browser."""
        # Send external jobs email if needed
        if (
            getattr(self._settings.application, "collect_external_jobs", False)
            and self._external_jobs
        ):
            from src.naukri_agent.utils.email_sender import send_external_jobs_email

            try:
                await asyncio.to_thread(
                    send_external_jobs_email, self._external_jobs, self._settings
                )
            except Exception as e:
                logger.error(f"Failed to send external jobs email: {e}")

        # Update run log
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
        from src.naukri_agent.utils.telemetry import MetricsTracker

        metrics = MetricsTracker(str(self._settings.project_root / self._settings.logging.log_dir))
        metrics.record_run(self._jobs_applied, self._jobs_failed)

        # Print summary
        self._print_summary()

        # Close browser
        if self._engine:
            try:
                await self._engine.close()
            except (PlaywrightTimeoutError, PlaywrightError) as e:
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
                f"  AI Matching: {'Enabled' if self._settings.ai.enable_matching else 'Disabled (Bulk Apply Mode)'}\n"
                f"  Dry Run: {'Yes' if self._settings.application.dry_run else 'No'}\n"
                f"  AI Model: {self._settings.ai.model}",
                border_style="cyan",
                padding=(1, 2),
            )
        )

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
                    run["keywords"][:30],
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
        finally:
            if self._engine:
                try:
                    await self._engine.close()
                except (PlaywrightTimeoutError, PlaywrightError) as e:
                    logger.debug(f"Browser close error: {e}")
