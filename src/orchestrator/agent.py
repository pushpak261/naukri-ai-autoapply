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
import heapq
import json
import re
import signal
import sys
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from src.ai.similarity import VectorSimilarityFilter
from src.browser.apply import JobApplier
from src.browser.search import JobSearcher
from src.config.constants import ApplicationStatus
from src.core.exceptions import LLMQuotaExceededError
from src.core.interfaces import IJobMatcher
from src.orchestrator.factory import DependencyFactory
from src.utils.helpers import random_delay
from src.utils.logger import (
    console,
    get_logger,
    log_error,
    log_info,
    log_step,
    log_success,
    log_warning,
    setup_logging,
)
import contextlib

logger = get_logger(__name__)


class NaukriAgent:
    """
    The main orchestration engine that coordinates all subsystems.

    Usage:
        factory = DependencyFactory(settings)
        agent = NaukriAgent(factory)
        await agent.run()
    """

    def __init__(self, factory: DependencyFactory) -> None:
        self._factory = factory
        self._settings = factory.get_settings()
        self._repo = factory.get_repository()
        self._engine = factory.get_browser_engine()
        self._resume_profile: dict | None = None
        self._run_log_id: int | None = None
        self._interrupted = False

        # Counters
        self._jobs_found = 0
        self._jobs_applied = 0
        self._jobs_skipped = 0
        self._jobs_failed = 0

        # Pre-compiled exclusion DFAs
        self._company_regex: re.Pattern[str] | None = None
        self._title_regex: re.Pattern[str] | None = None
        self._desc_regex: re.Pattern[str] | None = None

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

            login_handler = self._factory.create_login_handler()
            login_success = await login_handler.login()
            if not login_success:
                log_error("Login failed. Cannot proceed.")
                return

            # Step 4: Search for jobs
            searcher = self._factory.create_job_searcher()
            jobs = await searcher.search_all()
            self._jobs_found = len(jobs)

            if not jobs:
                log_warning("No jobs found matching your search criteria.")
                return

            log_success(f"Found {len(jobs)} candidate jobs. Starting evaluation...")

            # Pre-compile exclusion keywords into DFA for O(N) matching
            self._compile_exclusion_dfas()

            # Step 5: Initialize AI components
            matcher = self._factory.create_job_matcher()
            qa = self._factory.create_question_answerer(self._resume_profile)
            applier = self._factory.create_job_applier(qa)

            resume_text = (
                self._resume_profile.get("skills", [])
                + [self._resume_profile.get("current_title", "")]
                + [self._resume_profile.get("summary", "")]
            )
            vector_filter = VectorSimilarityFilter(resume_text)

            # Step 6: Process each job using Priority Queue Max-Heap
            await self._process_jobs(jobs, matcher, applier, searcher, vector_filter)

        except KeyboardInterrupt:
            log_warning("Agent interrupted by user (Ctrl+C)")
            self._interrupted = True
        except Exception as e:
            log_error(f"Agent error: {e}")
            logger.exception("Agent fatal error")
        finally:
            await self._cleanup()

    async def _parse_resume(self) -> None:
        """Parse the resume PDF and cache the structured profile."""
        resume_path = self._settings.resume.path
        if not resume_path:
            log_error("Resume path not configured. Set 'resume.path' in config.yaml")
            return

        path = Path(resume_path)
        if not path.exists():
            log_error(f"Resume file not found: {path}")
            return

        parser = self._factory.create_resume_parser()
        self._resume_profile = await parser.parse(str(path))

        if self._resume_profile:
            console.print(
                Panel(
                    f"[bold]{self._resume_profile.get('name', 'Unknown')}[/bold]\n"
                    f"Skills: {', '.join(self._resume_profile.get('skills', [])[:10])}...\n"
                    f"Experience: {self._resume_profile.get('total_experience_years', '?')} years\n"
                    f"Title: {self._resume_profile.get('current_title', 'N/A')}",
                    title="📄 Resume Profile",
                    border_style="cyan",
                )
            )

    async def _process_jobs(
        self,
        jobs: list[dict],
        matcher: IJobMatcher,
        applier: JobApplier,
        searcher: JobSearcher,
        vector_filter: VectorSimilarityFilter,
    ) -> None:
        """
        Process jobs optimally: Rank in Max-Heap, pre-filter with TF-IDF, then AI Match via Async Queue.
        """
        log_info("Building Max-Heap Priority Queue for optimal processing order...")
        assert self._resume_profile is not None, (
            "_process_jobs() requires a parsed resume profile; run() must "
            "check and return early before calling this."
        )
        resume_profile = self._resume_profile
        job_queue: list[tuple[float, int, dict]] = []
        for idx, job in enumerate(jobs):
            text_to_score = (
                f"{job.get('title', '')} {job.get('company', '')} {job.get('skills', '')}"
            )
            score = vector_filter.get_similarity_score(text_to_score)

            posted = str(job.get("posted_date", "")).lower()
            if "just now" in posted or "hour" in posted or "today" in posted or "1 day" in posted:
                score += 0.05

            heapq.heappush(job_queue, (-score, idx, job))

        total_jobs = len(job_queue)
        self._daily_applied = await self._repo.get_today_application_count() if self._repo else 0

        eval_queue: asyncio.Queue = asyncio.Queue()

        async def producer():
            processed_count = 0
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
                log_step(
                    processed_count,
                    total_jobs,
                    f"{job.get('title', '?')} @ {job.get('company', '?')} (Heuristic: {initial_score:.2f})",
                )

                if self._repo and self._repo.is_already_applied(job.get("naukri_job_id", "")):
                    self._jobs_skipped += 1
                    continue

                if self._is_excluded(job):
                    self._jobs_skipped += 1
                    continue

                if not job.get("description"):
                    details = await searcher.get_job_description(job["url"])
                    job["description"] = details.get("description", "")
                    if details.get("skills"):
                        job["skills"] = details["skills"]
                    await self._factory.get_browser_interactions().action_delay()

                full_text = (
                    f"{job.get('title', '')} {job.get('skills', '')} {job.get('description', '')}"
                )
                full_sim_score = vector_filter.get_similarity_score(full_text)

                if full_sim_score < 0.03:
                    self._jobs_skipped += 1
                    continue

                await eval_queue.put(job)

            await eval_queue.put(None)

        async def consumer():
            while True:
                if self._interrupted:
                    break
                job = await eval_queue.get()
                if job is None:
                    eval_queue.task_done()
                    break

                if not self._engine.is_alive():
                    log_warning(
                        "Browser disconnected during evaluation! Restarting browser engine..."
                    )
                    with contextlib.suppress(Exception):
                        await self._engine.close()
                    await self._engine.launch()
                    # Re-login just to be absolutely sure
                    try:
                        login_handler = self._factory.create_login_handler()
                        await login_handler.login()
                    except Exception as e:
                        logger.error(f"Failed to re-login after restart: {e}")
                # Enforce free-tier rate limits for Gemini (15 RPM -> wait >4s per request)
                # To be safe, wait 4.1 seconds between evaluations
                # Pacing AI requests to avoid Google's Free Tier 429 Rate Limit
                log_info("Pacing AI requests (waiting 6.5s) to avoid Google limits...")
                await asyncio.sleep(6.5)
                try:
                    match_result = await matcher.match(resume_profile, job)
                except LLMQuotaExceededError as e:
                    if e.is_daily_quota:
                        log_error(
                            "⚠️  Gemini's daily request quota is exhausted — stopping "
                            "the run here instead of marking every remaining job as a "
                            "non-match. See the error below for how to get more quota."
                        )
                    else:
                        log_error(
                            "⚠️  Gemini rate limit hit repeatedly — stopping the run "
                            "to avoid wasting further requests."
                        )
                    log_error(str(e))
                    self._interrupted = True
                    eval_queue.task_done()
                    break

                db_job = None
                if self._repo:
                    db_job = await self._repo.save_job(
                        naukri_job_id=job.get("naukri_job_id", ""),
                        title=job.get("title", ""),
                        company=job.get("company", ""),
                        url=job.get("url", ""),
                        location=job.get("location", ""),
                        experience=job.get("experience", ""),
                        salary=job.get("salary", ""),
                        description=job.get("description", ""),
                        skills=job.get("skills", ""),
                        posted_date=job.get("posted_date", ""),
                    )

                match_score = match_result.get("score", 0)
                should_apply = match_result.get("should_apply", False)

                if not should_apply:
                    if self._repo and db_job:
                        await self._repo.save_application(
                            job_id=db_job.id,
                            match_score=match_score,
                            status=ApplicationStatus.SKIPPED_LOW_SCORE,
                            match_reasoning=match_result.get("reasoning", ""),
                            matching_skills=", ".join(match_result.get("matching_skills", [])),
                            missing_skills=", ".join(match_result.get("missing_skills", [])),
                        )
                    self._jobs_skipped += 1
                    eval_queue.task_done()
                    continue

                if self._settings.application.dry_run:
                    log_info(f"DRY RUN — would apply (score: {match_score})")
                    if self._repo and db_job:
                        await self._repo.save_application(
                            job_id=db_job.id,
                            match_score=match_score,
                            status=ApplicationStatus.SKIPPED_DRY_RUN,
                            match_reasoning=match_result.get("reasoning", ""),
                            matching_skills=", ".join(match_result.get("matching_skills", [])),
                            missing_skills=", ".join(match_result.get("missing_skills", [])),
                        )
                    self._jobs_skipped += 1
                    eval_queue.task_done()
                    continue

                page = self._engine.page
                current_url = page.url
                if job["url"] not in current_url:
                    try:
                        await page.goto(job["url"], wait_until="domcontentloaded", timeout=60000)
                        await self._factory.get_browser_interactions().wait_for_navigation_complete()
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Failed to navigate to job page {job['url']}: {e}")
                        if self._repo and db_job:
                            await self._repo.save_application(
                                job_id=db_job.id,
                                match_score=match_score,
                                status=ApplicationStatus.FAILED,
                                match_reasoning=match_result.get("reasoning", ""),
                                matching_skills=", ".join(match_result.get("matching_skills", [])),
                                missing_skills=", ".join(match_result.get("missing_skills", [])),
                                error_message=f"Navigation failed: {e}",
                            )
                        self._jobs_failed += 1
                        eval_queue.task_done()
                        continue

                apply_result = await applier.apply_to_job(job)
                status = apply_result.get("status", ApplicationStatus.FAILED)
                error_msg = apply_result.get("error_message", "")

                if self._repo and db_job:
                    await self._repo.save_application(
                        job_id=db_job.id,
                        match_score=match_score,
                        status=status,
                        match_reasoning=match_result.get("reasoning", ""),
                        matching_skills=", ".join(match_result.get("matching_skills", [])),
                        missing_skills=", ".join(match_result.get("missing_skills", [])),
                        error_message=error_msg,
                    )

                if status == ApplicationStatus.APPLIED:
                    self._jobs_applied += 1
                    self._daily_applied += 1
                    await random_delay(
                        self._settings.application.delay_between_applies_min,
                        self._settings.application.delay_between_applies_max,
                    )
                elif status.startswith("skipped"):
                    self._jobs_skipped += 1
                else:
                    self._jobs_failed += 1

                eval_queue.task_done()

        producer_task = asyncio.create_task(producer())
        consumer_task = asyncio.create_task(consumer())
        await asyncio.gather(producer_task, consumer_task)

    def _compile_exclusion_dfas(self) -> None:
        """Compile exclusion keywords into DFA Regex for O(N) string matching."""
        exclusions = self._settings.exclusions

        if exclusions.companies:
            pattern = "|".join(map(re.escape, exclusions.companies))
            self._company_regex = re.compile(pattern, re.IGNORECASE)

        if exclusions.title_keywords:
            pattern = "|".join(map(re.escape, exclusions.title_keywords))
            self._title_regex = re.compile(pattern, re.IGNORECASE)

        if exclusions.description_keywords:
            pattern = "|".join(map(re.escape, exclusions.description_keywords))
            self._desc_regex = re.compile(pattern, re.IGNORECASE)

    def _is_excluded(self, job: dict) -> bool:
        """Check if a job matches any exclusion filters using O(N) DFA matching."""
        # Company exclusion
        company = job.get("company", "")
        if self._company_regex and self._company_regex.search(company):
            logger.info(f"Excluded company: {company}")
            return True

        # Title keyword exclusion
        title = job.get("title", "")
        if self._title_regex and self._title_regex.search(title):
            logger.info(f"Excluded title: {title}")
            return True

        # Description keyword exclusion
        description = job.get("description", "")
        if self._desc_regex and self._desc_regex.search(description):
            logger.info("Excluded description keyword")
            return True

        return False

    async def _cleanup(self) -> None:
        """Save state, update run log, print summary, and close browser."""
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
        from src.utils.telemetry import MetricsTracker

        metrics = MetricsTracker(str(self._settings.project_root / self._settings.logging.log_dir))
        metrics.record_run(self._jobs_applied, self._jobs_failed)

        # Print summary
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
    async def parse_resume_only(self, resume_path: str) -> dict | None:
        """Parse a resume and print the result without running the agent."""
        parser = self._factory.create_resume_parser()
        profile = await parser.parse(resume_path)

        if profile:
            console.print_json(json.dumps(profile, indent=2, ensure_ascii=False))
        return profile

    async def test_match(self, job_url: str) -> dict | None:
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
        login_handler = self._factory.create_login_handler()
        if not await login_handler.login():
            log_error("Login failed")
            await self._engine.close()
            return None

        # Get job description
        searcher = self._factory.create_job_searcher()
        details = await searcher.get_job_description(job_url)

        # Run matcher
        matcher = self._factory.create_job_matcher()
        job_data = {
            "title": "Test Job",
            "company": "Test Company",
            "url": job_url,
            **details,
        }
        result = await matcher.match(self._resume_profile, job_data)

        console.print_json(json.dumps(result, indent=2, ensure_ascii=False))

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

            login_handler = self._factory.create_login_handler()
            login_success = await login_handler.login()
            if not login_success:
                log_error("Login failed. Cannot proceed with profile refresh.")
                return

            # Execute profile refresh
            refresher = self._factory.create_profile_refresher()
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
                except Exception as e:
                    logger.debug(f"Browser close error: {e}")
