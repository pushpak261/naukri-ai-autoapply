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
import enum
import heapq
import json
import re
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table

from src.naukri_agent.utils.similarity import VectorSimilarityFilter
from src.naukri_agent.utils.company_legitimacy import PolicyLegitimacyEvaluator
from src.naukri_agent.browser.apply import JobApplier
from src.naukri_agent.browser.engine import WorkerBrowser, WorkerBrowserEngine
from src.naukri_agent.browser.gate import BrowserGate
from src.naukri_agent.browser.login import LoginHandler
from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.browser.profile import ProfileRefresher
from src.naukri_agent.browser.search import JobSearcher
from src.naukri_agent.config.constants import (
    ApplicationStatus,
    NAUKRI_DASHBOARD_URL,
    WORKER_GOTO_TIMEOUT,
    WORKER_NAV_SETTLE_TIMEOUT,
)
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.domain.entities import Job, JobApplication, ResumeProfile
from src.naukri_agent.core.domain.specifications import (
    AuthenticityExclusionSpecification,
    CompanyExclusionSpecification,
    ConsultancyScamSpecification,
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
from src.naukri_agent.bot.factory import ApplyWorkerStack, DependencyFactory
from src.naukri_agent.utils.helpers import TimeUtility, resolve_resume_path
from src.naukri_agent.utils.filters import (
    JobQualityFilter,
    parse_experience_range,
    parse_posted_age_days,
    ranges_overlap,
)
from src.naukri_agent.utils.job_metadata import merge_job_metadata
from src.naukri_agent.utils.rate_limiter import TokenBucketRateLimiter
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

_COUNTERS_INTERNAL_KEYS = frozenset({"force_persist"})

POLICY_REASON_MISSING_COMPANY_OR_TITLE = "missing_company_or_title_mismatch"
POLICY_REASON_RATING = "rating_below_threshold"
POLICY_REASON_AI = "ai_legitimacy_or_relevance_failed"
POLICY_REASON_EXPERIENCE = "experience_out_of_range"
POLICY_REASON_AGE = "older_than_7_days"


class ProcessOutcome(enum.Enum):
    CONTINUE = "continue"
    CAP_REACHED = "cap_reached"
    INTERRUPTED = "interrupted"


@dataclasses.dataclass
class ApplyWorker:
    id: int
    browser: WorkerBrowser
    stack: ApplyWorkerStack


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
        self._quality_filter: JobQualityFilter | None = None
        self._progress = progress_reporter or NullProgressReporter()
        self._phase = "idle"
        self._run_errored = False
        self._total_queued = 0
        self._cap_reached = False
        self._daily_applied = 0
        self._external_jobs: list[tuple[Job, str | None]] = []
        self._strict_policy_evaluator = PolicyLegitimacyEvaluator(self._llm)
        self._apply_workers: list[ApplyWorker] = []
        self._claim_lock = asyncio.Lock()
        self._cap_lock = asyncio.Lock()
        self._stats_lock = asyncio.Lock()
        self._in_flight_jobs: set[str] = set()
        self._llm_limiter: TokenBucketRateLimiter | None = None
        self._global_apply_limiter: TokenBucketRateLimiter | None = None
        self._workers_paused = asyncio.Event()
        self._workers_paused.set()
        self._last_progress_persist = 0.0

    def _progress_file_path(self) -> Path:
        return self._settings.project_root / "data" / "run_progress.json"

    def _clear_live_progress(self) -> None:
        with contextlib.suppress(OSError):
            self._progress_file_path().unlink(missing_ok=True)

    async def _persist_live_progress(self, **extra: Any) -> None:
        if not self._run_log_id:
            return

        now = time.monotonic()
        if now - self._last_progress_persist < 0.5 and not extra.get("force_persist"):
            return
        self._last_progress_persist = now

        from datetime import UTC, datetime

        async with self._stats_lock:
            processed_count = self._jobs_applied + self._jobs_skipped + self._jobs_failed
            payload = {
                "run_id": self._run_log_id,
                "phase": self._phase,
                "jobs_found": self._jobs_found,
                "jobs_applied": self._jobs_applied,
                "jobs_skipped": self._jobs_skipped,
                "jobs_failed": self._jobs_failed,
                "processed_count": extra.get("processed_count", processed_count),
                "total_queued": extra.get("total_queued", self._total_queued),
                "keywords": self._settings.search.keywords,
                "applied_jobs": list(self._applied_jobs_this_run[-50:]),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        progress_path = self._progress_file_path()

        def _write() -> None:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(json.dumps(payload), encoding="utf-8")

        await asyncio.to_thread(_write)

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
        counters_extra = {
            k: v for k, v in extra.items() if k not in _COUNTERS_INTERNAL_KEYS
        }
        payload.update(counters_extra)
        # region agent log
        try:
            import json
            import time

            _dbg_path = self._settings.project_root.parent / "debug-c1cca3.log"
            with open(_dbg_path, "a", encoding="utf-8") as _df:
                _df.write(
                    json.dumps(
                        {
                            "sessionId": "c1cca3",
                            "hypothesisId": "H1",
                            "location": "agent.py:_emit_counters",
                            "message": "emit_counters",
                            "data": {
                                "extra_keys": sorted(extra.keys()),
                                "payload_keys": sorted(payload.keys()),
                                "filtered_internal": sorted(
                                    k for k in extra if k in _COUNTERS_INTERNAL_KEYS
                                ),
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # endregion
        await self._emit(
            "counters_updated",
            counters_payload(self._run_log_id or 0, **payload),
        )
        await self._persist_live_progress(**extra)

    async def _resolve_apply_status(
        self,
        apply_result: dict,
        detail_page: JobDetailPage,
    ) -> tuple[str, str]:
        """Promote uncertain apply results when the page shows a successful application."""
        status = str(apply_result.get("status", ApplicationStatus.FAILED))
        error_msg = str(apply_result.get("error_message", "") or "")
        if status in (ApplicationStatus.UNCERTAIN, ApplicationStatus.ERROR):
            try:
                if await detail_page.is_already_applied():
                    return ApplicationStatus.APPLIED, ""
            except Exception as exc:
                logger.debug(f"Post-apply confirmation check failed: {exc}")
        return status, error_msg

    def _cap_remaining(self) -> int:
        return self._settings.application.daily_cap - getattr(self, "_daily_applied", 0)

    def _is_cap_reached(self) -> bool:
        return self._cap_remaining() <= 0

    async def _check_cap_reached(self) -> bool:
        async with self._cap_lock:
            return self._is_cap_reached()

    def _init_rate_limiters(self) -> None:
        app = self._settings.application
        self._llm_limiter = TokenBucketRateLimiter(
            capacity=app.rate_limit_capacity,
            refill_rate=app.rate_limit_refill_rate,
        )
        interval = max(app.global_apply_interval_sec, 1.0)
        self._global_apply_limiter = TokenBucketRateLimiter(capacity=1.0, refill_rate=1.0 / interval)

    async def _bootstrap_apply_workers(self, qa: IQuestionAnswerer) -> None:
        if not self._factory:
            raise RuntimeError("DependencyFactory required to bootstrap apply workers")
        if hasattr(self._engine, "capture_logged_in_session"):
            await self._engine.capture_logged_in_session()  # type: ignore[attr-defined]

        worker_count = self._settings.application.effective_apply_workers()
        self._apply_workers = []
        for i in range(worker_count):
            if not hasattr(self._engine, "new_worker_context"):
                raise RuntimeError("Browser engine does not support worker contexts")
            wb = await self._engine.new_worker_context(i)  # type: ignore[attr-defined]
            stack = self._factory.create_apply_worker_stack(WorkerBrowserEngine(wb), qa)
            worker = ApplyWorker(id=i, browser=wb, stack=stack)
            await self._warm_worker_session(worker)
            self._apply_workers.append(worker)
        log_info(f"Bootstrapped {len(self._apply_workers)} apply worker(s)")

    async def _warm_worker_session(
        self, worker: ApplyWorker, *, warm_dashboard: bool = True
    ) -> None:
        """Initialize worker tab with logged-in Naukri session.

        On timeout recovery, skip the dashboard hop so the next job navigation
        goes straight to the listing instead of flashing the home page.
        """
        page = worker.browser.page
        if page.is_closed():
            return
        if not warm_dashboard:
            return
        try:
            current = page.url or ""
            if current.startswith("about:") or not current.startswith("http"):
                await page.goto(
                    NAUKRI_DASHBOARD_URL,
                    wait_until="domcontentloaded",
                    timeout=WORKER_GOTO_TIMEOUT,
                )
                await worker.stack.interactions.wait_for_navigation_complete(
                    timeout=WORKER_NAV_SETTLE_TIMEOUT
                )
                log_info(f"[Worker-{worker.id}] Session warmed on Naukri dashboard")
        except Exception as e:
            log_warning(f"[Worker-{worker.id}] Session warm-up failed: {e}")

    @staticmethod
    def _resolve_job_url(job: Job) -> str:
        url = (job.url or "").strip()
        if url and not url.startswith("http"):
            url = f"https://www.naukri.com{url if url.startswith('/') else '/' + url}"
        return url

    def _worker_needs_job_navigation(self, page: Any, job: Job) -> bool:
        job_url = self._resolve_job_url(job)
        if not job_url:
            return False
        current = (page.url or "").strip()
        if not current or current.startswith("about:"):
            return True
        if job.naukri_job_id and job.naukri_job_id in current:
            return False
        return job_url not in current

    async def _navigate_worker_to_job(
        self,
        worker: ApplyWorker,
        job: Job,
        *,
        log_prefix: str,
    ) -> bool:
        """Navigate worker tab to the job detail page. Returns False if URL missing or navigation fails."""
        job_url = self._resolve_job_url(job)
        if not job_url:
            log_error(f"{log_prefix} Job {job.naukri_job_id} has no URL — cannot navigate")
            return False

        page = worker.browser.page
        if not self._worker_needs_job_navigation(page, job):
            return True

        detail_page = worker.stack.detail_page
        interactions = worker.stack.interactions
        try:
            await detail_page.navigate(job_url)
            job.url = job_url
            await detail_page.close_popups()
            current = page.url or ""
            if current.startswith("about:"):
                log_warning(f"{log_prefix} Still on blank page after navigate — retrying once")
                await page.goto(
                    job_url,
                    wait_until="domcontentloaded",
                    timeout=WORKER_GOTO_TIMEOUT,
                )
                await interactions.wait_for_navigation_complete(
                    timeout=WORKER_NAV_SETTLE_TIMEOUT
                )
                await asyncio.sleep(1)
            if (page.url or "").startswith("about:"):
                log_error(f"{log_prefix} Failed to leave about:blank for {job_url}")
                return False
            return True
        except Exception as e:
            log_error(f"{log_prefix} Failed to navigate worker to {job_url}: {e}")
            return False

    async def _restart_worker(self, worker: ApplyWorker, qa: IQuestionAnswerer) -> None:
        await worker.browser.close()
        if not self._factory or not hasattr(self._engine, "new_worker_context"):
            return
        wb = await self._engine.new_worker_context(worker.id)  # type: ignore[attr-defined]
        worker.browser = wb
        worker.stack = self._factory.create_apply_worker_stack(WorkerBrowserEngine(wb), qa)
        await self._warm_worker_session(worker, warm_dashboard=False)
        log_warning(f"[Worker-{worker.id}] Browser context restarted")

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
                cache_path = self._settings.project_root / "data" / "qa_cache.json"
                await self._repo.migrate_qa_cache_to_db(cache_path)
                self._clear_live_progress()
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

            self._init_rate_limiters()

            if self._resume_profile is None:
                raise RuntimeError("Resume profile not loaded.")
            qa = self._question_answerer_factory(self._resume_profile)
            await self._bootstrap_apply_workers(qa)

            # Step 4–6: Pipeline search batches into apply while searching continues
            self._phase = "searching"
            await self._emit_counters()
            await self._emit("search_started", {})
            searcher = self._job_searcher
            if not searcher:
                raise RuntimeError("JobSearcher not configured.")

            exclusions = self._settings.exclusions
            self._exclusion_spec = (
                CompanyExclusionSpecification(exclusions.companies)
                | TitleExclusionSpecification(exclusions.title_keywords)
                | DescriptionExclusionSpecification(exclusions.description_keywords)
                | AuthenticityExclusionSpecification(
                    exclusions.fake_company_blocklist, exclusions.max_openings_without_logo
                )
            )
            if exclusions.enable_scam_filter:
                self._exclusion_spec |= ConsultancyScamSpecification()
            self._quality_filter = JobQualityFilter(
                require_verified=False,
                min_company_rating=self._settings.application.min_company_rating,
            )

            matcher = self._job_matcher
            if not matcher:
                raise RuntimeError("JobMatcher not configured.")
            if self._question_answerer_factory is None:
                raise RuntimeError("QuestionAnswerer factory not configured.")
            if self._job_applier_factory is None:
                raise RuntimeError("JobApplier factory not configured.")

            if self._resume_profile is None:
                raise RuntimeError("Resume profile not loaded.")

            resume_text = (
                self._resume_profile.skills
                + [self._resume_profile.current_title]
                + [self._resume_profile.summary]
            )
            doc_frequencies: dict[str, int] = {}
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
                resume_text,
                doc_frequencies=doc_frequencies,
                total_documents=total_documents,
            )

            await self._run_search_apply_pipeline(searcher, matcher, vector_filter)

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
        path = resolve_resume_path(self._settings)
        if not path:
            log_error(
                "Resume file not found. Place your resume at data/resumes/resume.pdf "
                "or set 'resume.path' in config.yaml"
            )
            return

        log_info(f"Using resume file: {path}")

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

    async def _init_daily_applied(self) -> None:
        if self._settings.run_cap_resets_daily:
            self._daily_applied = 0
        else:
            self._daily_applied = (
                await self._repo.get_today_application_count() if self._repo else 0
            )

    def _rank_batch_jobs(
        self,
        jobs: list[Job],
        vector_filter: VectorSimilarityFilter,
    ) -> list[Job]:
        """Rank jobs within a search batch by TF-IDF similarity (highest first)."""
        job_heap: list[tuple[float, int, Job]] = []
        for idx, job in enumerate(jobs):
            text_to_score = f"{job.title} {job.company} {job.skills}"
            score = vector_filter.get_similarity_score(text_to_score)
            posted = str(job.posted_date).lower()
            if "just now" in posted or "hour" in posted or "today" in posted or "1 day" in posted:
                score += 0.05
            heapq.heappush(job_heap, (-score, idx, job))

        ranked: list[Job] = []
        while job_heap:
            _, _, job = heapq.heappop(job_heap)
            ranked.append(job)
        return ranked

    async def _run_search_apply_pipeline(
        self,
        searcher: JobSearcher,
        matcher: IJobMatcher,
        vector_filter: VectorSimilarityFilter,
    ) -> None:
        await self._init_daily_applied()
        self._total_queued = 0
        self._cap_reached = False

        gate = BrowserGate()
        queue: asyncio.Queue[Job | None] = asyncio.Queue()

        consumers = [
            asyncio.create_task(
                self._apply_worker_loop(worker, queue, matcher, vector_filter)
            )
            for worker in self._apply_workers
        ]
        await asyncio.gather(
            self._search_producer(searcher, queue, gate, vector_filter),
            *consumers,
        )

        if self._jobs_found == 0:
            log_warning("No jobs found matching your search criteria.")

    async def _search_producer(
        self,
        searcher: JobSearcher,
        queue: asyncio.Queue[Job | None],
        gate: BrowserGate,
        vector_filter: VectorSimilarityFilter,
    ) -> None:
        try:
            async for batch in searcher.iter_search_batches(browser_gate=gate):
                if self._interrupted or self._cap_reached or self._is_cap_reached():
                    break

                ranked_jobs = self._rank_batch_jobs(batch.jobs, vector_filter)
                for job in ranked_jobs:
                    await self._emit_job(job, "queued")
                    await queue.put(job)
                    self._total_queued += 1

                self._jobs_found += len(batch.jobs)
                await self._emit(
                    "search_batch_completed",
                    {
                        "keyword": batch.keyword,
                        "location": batch.location,
                        "batch_jobs": len(batch.jobs),
                        "total_unique": self._jobs_found,
                    },
                )
                await self._emit_counters(
                    jobs_found=self._jobs_found,
                    total_queued=self._total_queued,
                )

                if batch.jobs and self._phase == "searching":
                    self._phase = "searching_and_applying"
                    log_success(
                        f"Found {len(batch.jobs)} jobs for '{batch.keyword}' in "
                        f"'{batch.location}'. Starting evaluation while searching continues..."
                    )
        finally:
            for _ in self._apply_workers:
                await queue.put(None)
            await self._emit("search_completed", {"jobs_found": self._jobs_found})
            await self._emit_counters(jobs_found=self._jobs_found, total_queued=self._total_queued)
            if not self._interrupted and self._total_queued > 0:
                self._phase = "processing"

    async def _apply_worker_loop(
        self,
        worker: ApplyWorker,
        queue: asyncio.Queue[Job | None],
        matcher: IJobMatcher,
        vector_filter: VectorSimilarityFilter,
    ) -> None:
        processed_count = 0
        prefix = f"[Worker-{worker.id}]"

        while True:
            if self._interrupted:
                break

            job = await queue.get()
            try:
                if job is None:
                    break

                await self._workers_paused.wait()

                if await self._check_cap_reached():
                    async with self._cap_lock:
                        self._cap_reached = True
                    break

                processed_count += 1
                text_to_score = f"{job.title} {job.company} {job.skills}"
                initial_score = vector_filter.get_similarity_score(text_to_score)

                job_timeout = self._settings.application.job_processing_timeout_sec
                job_task = asyncio.create_task(
                    self._process_one_job(
                        job,
                        initial_score=initial_score,
                        processed_count=processed_count,
                        total_queued=self._total_queued,
                        matcher=matcher,
                        vector_filter=vector_filter,
                        worker=worker,
                    )
                )
                try:
                    outcome = await asyncio.wait_for(job_task, timeout=job_timeout)
                except TimeoutError:
                    log_warning(
                        f"{prefix} Timed out processing job {job.naukri_job_id} "
                        f"after {job_timeout}s"
                    )
                    job_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await job_task
                    async with self._stats_lock:
                        self._jobs_failed += 1
                    if self._factory and self._resume_profile:
                        qa = self._question_answerer_factory(self._resume_profile)
                        await self._restart_worker(worker, qa)
                    continue

                if outcome == ProcessOutcome.CAP_REACHED:
                    async with self._cap_lock:
                        self._cap_reached = True
                    break
                if outcome == ProcessOutcome.INTERRUPTED:
                    break
            finally:
                queue.task_done()

    async def _process_jobs(
        self,
        jobs: list[Job],
        matcher: IJobMatcher,
        applier: JobApplier,
        searcher: JobSearcher,
        vector_filter: VectorSimilarityFilter,
    ) -> None:
        """Legacy sequential path — requires bootstrapped apply workers."""
        if not self._apply_workers:
            raise RuntimeError("Apply workers not bootstrapped")
        worker = self._apply_workers[0]
        log_info("Building Max-Heap Priority Queue for optimal processing order...")
        assert self._resume_profile is not None

        ranked_jobs = self._rank_batch_jobs(jobs, vector_filter)
        total_jobs = len(ranked_jobs)
        await self._init_daily_applied()
        processed_count = 0

        for job in ranked_jobs:
            await self._emit_job(job, "queued")

        for job in ranked_jobs:
            if self._interrupted:
                break
            if await self._check_cap_reached():
                log_warning(
                    f"Application cap reached ({self._settings.application.daily_cap}). Stopping."
                )
                break

            processed_count += 1
            text_to_score = f"{job.title} {job.company} {job.skills}"
            initial_score = vector_filter.get_similarity_score(text_to_score)

            outcome = await self._process_one_job(
                job,
                initial_score=initial_score,
                processed_count=processed_count,
                total_queued=total_jobs,
                matcher=matcher,
                vector_filter=vector_filter,
                worker=worker,
            )

            if outcome in (ProcessOutcome.CAP_REACHED, ProcessOutcome.INTERRUPTED):
                break

    async def _process_one_job(
        self,
        job: Job,
        *,
        initial_score: float,
        processed_count: int,
        total_queued: int,
        matcher: IJobMatcher,
        vector_filter: VectorSimilarityFilter,
        worker: ApplyWorker,
    ) -> ProcessOutcome:
        assert self._resume_profile is not None
        resume_profile = self._resume_profile
        worker_id = worker.id
        applier = worker.stack.applier
        interactions = worker.stack.interactions
        detail_page = worker.stack.detail_page
        page = worker.browser.page
        log_prefix = f"[Worker-{worker_id}]"

        await self._emit_job(
            job, "processing", heuristic_score=initial_score, worker_id=worker_id
        )
        async with self._stats_lock:
            await self._emit_counters(
                jobs_found=self._jobs_found,
                processed_count=processed_count,
                total_queued=total_queued,
            )
        log_step(
            processed_count,
            total_queued,
            f"{log_prefix} {job.title} @ {job.company} (Heuristic: {initial_score:.2f})",
        )

        if self._settings.application.strict_policy_mode:
            title_ok = self._title_matches_keywords(job.title)
            if not job.company or not title_ok:
                self._log_policy_decision(
                    stage="company_title",
                    decision="fail",
                    reason_code=POLICY_REASON_MISSING_COMPANY_OR_TITLE,
                    job=job,
                    details={},
                )
                async with self._stats_lock:
                    self._jobs_skipped += 1
                await self._emit_job(
                    job, "skipped_policy", heuristic_score=initial_score, worker_id=worker_id
                )
                return ProcessOutcome.CONTINUE
        else:
            whitelist = self._settings.exclusions.title_whitelist
            if whitelist and isinstance(whitelist, (list, set, tuple)):
                title_lower = (job.title or "").lower()
                if not any(kw.lower() in title_lower for kw in whitelist):
                    log_info(
                        f"{log_prefix} Skipping job: title '{job.title}' "
                        "does not match whitelist keywords"
                    )
                    async with self._stats_lock:
                        self._jobs_skipped += 1
                    return ProcessOutcome.CONTINUE

        async with self._claim_lock:
            if self._repo and (
                self._repo.is_already_applied(job.naukri_job_id)
                or job.naukri_job_id in self._in_flight_jobs
            ):
                async with self._stats_lock:
                    self._jobs_skipped += 1
                await self._emit_job(
                    job, "skipped_already_applied", heuristic_score=initial_score, worker_id=worker_id
                )
                return ProcessOutcome.CONTINUE
            if self._repo and self._repo.is_already_applied_composite(job.title, job.company):
                async with self._stats_lock:
                    self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    "skipped_already_applied",
                    heuristic_score=initial_score,
                    reason="Composite title+company already applied",
                    worker_id=worker_id,
                )
                return ProcessOutcome.CONTINUE
            self._in_flight_jobs.add(job.naukri_job_id)

        try:
            return await self._process_one_job_inner(
                job,
                initial_score=initial_score,
                processed_count=processed_count,
                total_queued=total_queued,
                matcher=matcher,
                vector_filter=vector_filter,
                worker=worker,
                resume_profile=resume_profile,
                applier=applier,
                interactions=interactions,
                detail_page=detail_page,
                page=page,
                log_prefix=log_prefix,
                worker_id=worker_id,
            )
        finally:
            self._in_flight_jobs.discard(job.naukri_job_id)

    async def _process_one_job_inner(
        self,
        job: Job,
        *,
        initial_score: float,
        processed_count: int,
        total_queued: int,
        matcher: IJobMatcher,
        vector_filter: VectorSimilarityFilter,
        worker: ApplyWorker,
        resume_profile: ResumeProfile,
        applier: JobApplier,
        interactions: Any,
        detail_page: Any,
        page: Any,
        log_prefix: str,
        worker_id: int,
    ) -> ProcessOutcome:
        if (not self._settings.application.strict_policy_mode) and self._is_excluded(job):
            async with self._stats_lock:
                self._jobs_skipped += 1
            await self._emit_job(
                job,
                "skipped_excluded",
                heuristic_score=initial_score,
                reason="Excluded by company/title/description filter",
                worker_id=worker_id,
            )
            return ProcessOutcome.CONTINUE

        if not page.is_closed():
            pass

        job_url = self._resolve_job_url(job)
        if not job_url:
            async with self._stats_lock:
                self._jobs_failed += 1
            await self._emit_job(
                job,
                "failed",
                heuristic_score=initial_score,
                reason="Missing job URL",
                worker_id=worker_id,
            )
            return ProcessOutcome.CONTINUE

        needs_detail_page = (
            not job.description
            or job.company_rating is None
            or job.is_external_apply is None
        )
        if needs_detail_page or self._worker_needs_job_navigation(page, job):
            if not await self._navigate_worker_to_job(
                worker, job, log_prefix=log_prefix
            ):
                async with self._stats_lock:
                    self._jobs_failed += 1
                await self._emit_job(
                    job,
                    "failed",
                    heuristic_score=initial_score,
                    reason="Worker could not open job detail page",
                    worker_id=worker_id,
                )
                return ProcessOutcome.CONTINUE
            try:
                details = await detail_page.get_job_details()
            except Exception as e:
                logger.error(f"{log_prefix} Failed to fetch job details from {job_url}: {e}")
                details = {}
            if details.get("description"):
                job.description = details["description"]
            if details.get("skills"):
                job.skills = details["skills"]
            if details.get("openings") is not None:
                job.openings = details.get("openings", 0)
            if details.get("has_company_logo") is not None:
                job.has_company_logo = details.get("has_company_logo", False)
            merge_job_metadata(
                job,
                rating=details.get("company_rating"),
                verified=details.get("is_verified"),
                is_external_apply=details.get("is_external_apply"),
                external_apply_url=details.get("external_apply_url"),
            )
            await interactions.action_delay()

        if (not self._settings.application.strict_policy_mode) and self._is_excluded(job):
            async with self._stats_lock:
                self._jobs_skipped += 1
            await self._emit_job(
                job,
                "skipped_excluded",
                heuristic_score=initial_score,
                reason="Excluded after fetching details",
                worker_id=worker_id,
            )
            return ProcessOutcome.CONTINUE

        if self._settings.application.strict_policy_mode:
            strict_eval = await self._evaluate_strict_policy(job)
            if not strict_eval["passed"]:
                async with self._stats_lock:
                    self._jobs_skipped += 1
                return ProcessOutcome.CONTINUE

        if job.is_external_apply:
            if getattr(self._settings.application, "collect_external_jobs", False):
                self._external_jobs.append((job, job.external_apply_url))
            async with self._stats_lock:
                self._jobs_skipped += 1
            await self._emit_job(
                job,
                ApplicationStatus.EXTERNAL_APPLY,
                heuristic_score=initial_score,
                reason="External apply — apply on company site",
                worker_id=worker_id,
            )
            return ProcessOutcome.CONTINUE

        if self._quality_filter and not self._settings.application.strict_policy_mode:
            passes_quality, skip_reason = self._quality_filter.evaluate(job)
            if not passes_quality:
                log_warning(f"{log_prefix} Skipping {job.title} @ {job.company}: {skip_reason}")
                async with self._stats_lock:
                    self._jobs_skipped += 1
                await self._emit_job(
                    job,
                    ApplicationStatus.SKIPPED_LOW_COMPANY_RATING
                    if "rating" in skip_reason.lower()
                    else "skipped_quality",
                    heuristic_score=initial_score,
                    reason=skip_reason,
                    worker_id=worker_id,
                )
                return ProcessOutcome.CONTINUE

        full_text = f"{job.title} {job.skills} {job.description}"
        full_sim_score = vector_filter.get_similarity_score(full_text)
        sim_threshold = 0.04 if not self._settings.application.strict_policy_mode else 0.03

        if full_sim_score < sim_threshold:
            async with self._stats_lock:
                self._jobs_skipped += 1
            await self._emit_job(
                job,
                "skipped_similarity",
                heuristic_score=initial_score,
                reason="TF-IDF similarity below threshold",
                worker_id=worker_id,
            )
            return ProcessOutcome.CONTINUE

        if await self._check_cap_reached():
            log_warning(
                f"Application cap reached ({self._settings.application.daily_cap}). Stopping."
            )
            return ProcessOutcome.CAP_REACHED

        await self._emit_job(job, "matching", heuristic_score=initial_score, worker_id=worker_id)
        if self._llm_limiter:
            await self._llm_limiter.acquire()

        try:
            match_result = await matcher.match(resume_profile, job)
        except (LLMQuotaExceededError, LLMAPIError) as e:
            is_daily = isinstance(e, LLMQuotaExceededError) and e.is_daily_quota

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

                llm_provider = self._llm
                if not llm_provider:
                    raise RuntimeError("LLMProvider not configured.") from e
                if hasattr(llm_provider, "set_model"):
                    llm_provider.set_model(fallback_model)

                self._settings.ai.model = fallback_model
                self._settings.ai.fallback_model = None

                try:
                    match_result = await matcher.match(resume_profile, job)
                except Exception as fallback_err:
                    logger.error(f"AI Match failed on fallback model: {fallback_err}")
                    async with self._stats_lock:
                        self._jobs_failed += 1
                    return ProcessOutcome.CONTINUE
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
                            return ProcessOutcome.INTERRUPTED
                        log_warning(
                            f"⚠️  Gemini's daily request quota is exhausted for model "
                            f"'{self._settings.ai.model}', but continuing run "
                            "(abort_on_quota is False)."
                        )
                        async with self._stats_lock:
                            self._jobs_failed += 1
                        return ProcessOutcome.CONTINUE
                    log_error(
                        "⚠️  Gemini rate limit hit repeatedly — stopping the run "
                        "to avoid wasting further requests."
                    )
                    log_error(str(e))
                    self._interrupted = True
                    return ProcessOutcome.INTERRUPTED
                log_error(f"⚠️  Gemini API error occurred: {e}")
                async with self._stats_lock:
                    self._jobs_failed += 1
                return ProcessOutcome.CONTINUE
        except Exception as e:
            logger.error(f"AI Match failed: {e}")
            async with self._stats_lock:
                self._jobs_failed += 1
            return ProcessOutcome.CONTINUE

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
            job.id = db_job.id

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
            async with self._stats_lock:
                self._jobs_skipped += 1
            await self._emit_job(
                job,
                "skipped_low_score",
                heuristic_score=initial_score,
                match_score=match_score,
                match_reasoning=match_result.match_reasoning,
                worker_id=worker_id,
            )
            return ProcessOutcome.CONTINUE

        if self._settings.application.dry_run:
            log_info(f"{log_prefix} DRY RUN — would apply (score: {match_score})")
            async with self._cap_lock:
                self._daily_applied += 1
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
            async with self._stats_lock:
                self._jobs_skipped += 1
            await self._emit_job(
                job,
                "skipped_dry_run",
                heuristic_score=initial_score,
                match_score=match_score,
                match_reasoning=match_result.match_reasoning,
                worker_id=worker_id,
            )
            return ProcessOutcome.CONTINUE

        if self._global_apply_limiter:
            await self._global_apply_limiter.acquire()

        async def _navigate_and_apply() -> dict:
            if not await self._navigate_worker_to_job(
                worker, job, log_prefix=log_prefix
            ):
                if self._repo and db_job:
                    assert db_job.id is not None
                    await self._repo.save_application(
                        job_id=db_job.id,
                        match_score=match_score,
                        status=ApplicationStatus.FAILED,
                        match_reasoning=match_result.match_reasoning,
                        matching_skills=match_result.matching_skills,
                        missing_skills=match_result.missing_skills,
                        error_message="Worker could not open job detail page",
                    )
                async with self._stats_lock:
                    self._jobs_failed += 1
                await self._emit_job(
                    job,
                    "failed",
                    heuristic_score=initial_score,
                    match_score=match_score,
                    reason="Worker could not open job detail page",
                    worker_id=worker_id,
                )
                return {
                    "status": ApplicationStatus.FAILED,
                    "error_message": "Navigation failed: worker stuck on blank page",
                }

            log_info(f"{log_prefix} Applying to: {job.title} @ {job.company}")
            await self._emit(
                "applying",
                {
                    "worker_id": worker_id,
                    "job_id": job.naukri_job_id,
                    "title": job.title,
                    "company": job.company,
                },
            )
            await self._emit_job(
                job,
                "applying",
                heuristic_score=initial_score,
                match_score=match_score,
                match_reasoning=match_result.match_reasoning,
                worker_id=worker_id,
            )
            return await applier.apply_to_job(job)

        apply_result = await _navigate_and_apply()

        if apply_result.get("status") == ApplicationStatus.FAILED and "Navigation failed" in str(
            apply_result.get("error_message", "")
        ):
            return ProcessOutcome.CONTINUE

        status, error_msg = await self._resolve_apply_status(apply_result, detail_page)

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
            async with self._stats_lock:
                self._jobs_applied += 1
            async with self._cap_lock:
                self._daily_applied += 1
            await self._emit_job(
                job,
                "applied",
                heuristic_score=initial_score,
                match_score=match_score,
                match_reasoning=match_result.match_reasoning,
                worker_id=worker_id,
            )
            async with self._stats_lock:
                self._applied_jobs_this_run.append(
                    {
                        "naukri_job_id": job.naukri_job_id,
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
            if status == ApplicationStatus.SKIPPED_EXTERNAL:
                ext_url = apply_result.get("external_url")
                self._external_jobs.append((job, ext_url))
            elif status == ApplicationStatus.SKIPPED_SCREENING:
                if not getattr(self._settings.application, "answer_questions_with_pdf", True):
                    self._external_jobs.append((job, None))
            async with self._stats_lock:
                self._jobs_skipped += 1
            await self._emit_job(
                job,
                status,
                heuristic_score=initial_score,
                match_score=match_score,
                match_reasoning=match_result.match_reasoning,
                reason=error_msg or None,
                worker_id=worker_id,
            )
        else:
            async with self._stats_lock:
                self._jobs_failed += 1
            if getattr(self._settings.application, "collect_external_jobs", False):
                self._external_jobs.append((job, None))
            await self._emit_job(
                job,
                "failed",
                heuristic_score=initial_score,
                match_score=match_score,
                match_reasoning=match_result.match_reasoning,
                reason=error_msg or None,
                worker_id=worker_id,
            )
        await self._emit_counters(
            jobs_found=self._jobs_found,
            processed_count=processed_count,
            total_queued=total_queued,
            force_persist=True,
        )
        return ProcessOutcome.CONTINUE

    def _is_excluded(self, job: Job) -> bool:
        """Check if a job matches any exclusion specifications."""
        if not self._exclusion_spec:
            return False
        return self._exclusion_spec.is_satisfied_by(job)

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _title_matches_keywords(self, title: str) -> bool:
        norm_title = self._normalize_text(title)
        if not norm_title:
            return False
        title_tokens = set(norm_title.split())
        for keyword in self._settings.search.keywords:
            norm_kw = self._normalize_text(keyword)
            if not norm_kw:
                continue
            if norm_kw in norm_title:
                return True
            kw_tokens = set(norm_kw.split())
            if kw_tokens and len(title_tokens & kw_tokens) >= max(1, len(kw_tokens) - 1):
                return True
        return False

    def _log_policy_decision(
        self,
        *,
        stage: str,
        decision: str,
        reason_code: str | None,
        job: Job,
        details: dict[str, Any],
    ) -> None:
        logger.info(
            "strict_policy_decision",
            extra={
                "policy_stage": stage,
                "decision": decision,
                "skip_reason_code": reason_code,
                "job_id": job.naukri_job_id,
                "title": job.title,
                "company": job.company,
                "details": details,
            },
        )

    async def _evaluate_strict_policy(self, job: Job) -> dict[str, Any]:
        if not job.company or not self._title_matches_keywords(job.title):
            self._log_policy_decision(
                stage="company_title",
                decision="fail",
                reason_code=POLICY_REASON_MISSING_COMPANY_OR_TITLE,
                job=job,
                details={},
            )
            return {"passed": False, "reason_code": POLICY_REASON_MISSING_COMPANY_OR_TITLE}

        min_rating = self._settings.application.min_company_rating
        if job.company_rating is None or job.company_rating <= min_rating:
            self._log_policy_decision(
                stage="rating",
                decision="fail",
                reason_code=POLICY_REASON_RATING,
                job=job,
                details={"rating": job.company_rating, "required_gt": min_rating},
            )
            return {"passed": False, "reason_code": POLICY_REASON_RATING}

        ai_result = await self._strict_policy_evaluator.evaluate(
            company=job.company,
            title=job.title,
            description=job.description,
        )
        if not (
            ai_result.get("is_legit_company", False)
            and ai_result.get("is_post_relevant_to_company", False)
        ):
            self._log_policy_decision(
                stage="ai_legitimacy_relevance",
                decision="fail",
                reason_code=POLICY_REASON_AI,
                job=job,
                details=ai_result,
            )
            return {"passed": False, "reason_code": POLICY_REASON_AI}

        user_min = self._settings.search.experience_min
        user_max = self._settings.search.experience_max
        parsed_exp = parse_experience_range(job.experience)
        if parsed_exp is None or not ranges_overlap(parsed_exp[0], parsed_exp[1], user_min, user_max):
            self._log_policy_decision(
                stage="experience",
                decision="fail",
                reason_code=POLICY_REASON_EXPERIENCE,
                job=job,
                details={
                    "job_experience": job.experience,
                    "parsed_experience": parsed_exp,
                    "user_range": [user_min, user_max],
                },
            )
            return {"passed": False, "reason_code": POLICY_REASON_EXPERIENCE}

        age_days = parse_posted_age_days(job.posted_date)
        if age_days is None or age_days > 7:
            self._log_policy_decision(
                stage="freshness",
                decision="fail",
                reason_code=POLICY_REASON_AGE,
                job=job,
                details={"posted_date": job.posted_date, "age_days": age_days},
            )
            return {"passed": False, "reason_code": POLICY_REASON_AGE}

        self._log_policy_decision(
            stage="final",
            decision="pass",
            reason_code=None,
            job=job,
            details={"age_days": age_days, "parsed_experience": parsed_exp, "rating": job.company_rating},
        )
        return {"passed": True, "reason_code": None}

    async def _cleanup(self) -> None:
        """Save state, update run log, print summary, and close browser."""
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

        for worker in self._apply_workers:
            try:
                await worker.browser.close()
            except Exception as e:
                logger.debug(f"Worker-{worker.id} cleanup error: {e}")
        self._apply_workers.clear()

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

        self._clear_live_progress()

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
