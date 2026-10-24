"""
CLI entry point for the LinkedIn Agent.
Uses Click + Rich for terminal UI.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.panel import Panel

from src.linked_agent.utils.logger import console, setup_logging


def _run_async(coro):
    """Run an async function from a sync Click command."""
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")


@click.group()
def cli():
    """LinkedIn Auto-Apply Agent — AI-powered job application automation."""
    pass


@cli.command()
@click.option("--dry-run", is_flag=True, help="Score jobs but don't actually apply.")
@click.option("--config", "config_path", default=None, help="Path to config.yaml")
def run(dry_run: bool, config_path: str | None) -> None:
    """Run the LinkedIn agent — search, match, and apply to jobs."""
    async def _run():
        from src.linked_agent.config.settings import get_settings
        from src.linked_agent.models.db_schema import setup_database_manager
        from src.linked_agent.bot.factory import LinkedInDependencyFactory
        from src.linked_agent.bot.agent import LinkedInAgent

        setup_logging(level="INFO", log_to_file=True)

        settings = get_settings()
        problems = settings.validate_required()
        if problems:
            console.print(Panel(
                "\n".join(f"  - {p}" for p in problems),
                title="Configuration Issues",
                border_style="red",
            ))
            sys.exit(1)

        db_manager = await setup_database_manager(settings.db_path)

        # Connect to Naukri DB for write-through so the frontend can see LinkedIn data
        naukri_db_manager = None
        try:
            naukri_db_path = settings.project_root / "data" / "naukri_agent.db"
            if naukri_db_path.exists():
                from src.naukri_agent.models.db_schema import (
                    setup_database_manager as setup_naukri_db,
                )
                naukri_db_manager = await setup_naukri_db(naukri_db_path)
        except Exception as exc:
            console.print(f"[yellow]Warning: could not open Naukri DB for write-through: {exc}[/yellow]")

        factory = LinkedInDependencyFactory(
            settings,
            db_manager=db_manager,
            naukri_db_manager=naukri_db_manager,
        )
        agent = LinkedInAgent(factory=factory)
        from api.job_queue import run_selected_jobs

        await run_selected_jobs(agent, naukri_db_manager, "linkedin", dry_run=dry_run)

    _run_async(_run())


@cli.command()
@click.argument("resume_path")
def parse(resume_path: str) -> None:
    """Parse a resume PDF and display the structured profile."""
    async def _parse():
        from src.linked_agent.config.settings import get_settings
        from src.linked_agent.models.db_schema import setup_database_manager
        from src.linked_agent.bot.factory import LinkedInDependencyFactory
        from src.linked_agent.bot.agent import LinkedInAgent

        settings = get_settings()
        db_manager = await setup_database_manager(settings.db_path)
        factory = LinkedInDependencyFactory(settings, db_manager=db_manager)
        agent = LinkedInAgent(factory=factory)
        await agent.parse_resume_only(resume_path)

    _run_async(_parse())


@cli.command()
def status() -> None:
    """Display application statistics from the database."""
    async def _status():
        from src.linked_agent.config.settings import get_settings
        from src.linked_agent.models.db_schema import setup_database_manager
        from src.linked_agent.bot.factory import LinkedInDependencyFactory
        from rich.table import Table

        settings = get_settings()
        db_manager = await setup_database_manager(settings.db_path)
        factory = LinkedInDependencyFactory(settings, db_manager=db_manager)
        repo = factory.get_repository()
        await repo.initialize()

        stats = await repo.get_application_stats(days=7)
        table = Table(title="Application Stats (Last 7 Days)", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Total", str(stats["total"]))
        table.add_row("Applied", str(stats["applied"]))
        table.add_row("Skipped", str(stats["skipped"]))
        table.add_row("Failed", str(stats["failed"]))
        console.print(table)

    _run_async(_status())


@cli.command()
def init() -> None:
    """Initialize the LinkedIn agent configuration."""
    config_template = """# LinkedIn Auto-Apply Agent Configuration
# ==========================================

linkedin:
  email: ""  # Or set LINKEDIN_EMAIL in .env
  password: ""  # Or set LINKEDIN_PASSWORD in .env

ai:
  use_gemini: false
  gemini_api_key: ""  # Or set GEMINI_API_KEY in .env
  model: "gemini-3.5-flash"
  fallback_model: null
  enable_matching: true
  abort_on_quota: true
  temperature: 0.3
  max_output_tokens: 4096

resume:
  path: "resume.pdf"

search:
  keywords:
    - "Software Engineer"
    - "Python Developer"
  locations:
    - "United States"
    - "Remote"
  experience_level: []
  job_type: []
  work_type: ""  # on_site, remote, hybrid
  freshness: "past_week"  # any, past_24h, past_week, past_month
  max_pages: 3
  sort_by: "relevance"  # relevance, date
  enable_heuristics: true

application:
  daily_cap: 50
  match_score_threshold: 70
  answer_questions_with_pdf: true
  delay_between_applies_min: 60
  delay_between_applies_max: 180
  delay_between_actions_min: 3.0
  delay_between_actions_max: 8.0
  skip_external_apply: true
  collect_external_jobs: true
  easy_apply_only: false
  unfollow_after_apply: true
  dry_run: false
  max_retries: 3
  rate_limit_capacity: 5.0
  rate_limit_refill_rate: 0.5

profile:
  current_ctc: ""
  expected_ctc: ""
  notice_period: "30 days"
  current_location: ""
  preferred_locations: []
  total_experience: ""

exclusions:
  enable_scam_filter: true
  companies: []
  title_keywords: []
  description_keywords: []
  fake_company_blocklist: []

logging:
  level: "INFO"
  log_to_file: true
  log_dir: "data/logs"
"""

    config_path = Path("linkedin_config.yaml")
    if config_path.exists():
        console.print("[yellow]linkedin_config.yaml already exists. Skipping.[/yellow]")
        return

    config_path.write_text(config_template, encoding="utf-8")
    console.print("[green]Created linkedin_config.yaml[/green]")

    # Create .env template if it doesn't exist
    env_path = Path(".env")
    if not env_path.exists():
        env_template = """# LinkedIn Agent Environment Variables
LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=
GEMINI_API_KEY=
SESSION_ENCRYPTION_KEY=
"""
        env_path.write_text(env_template, encoding="utf-8")
        console.print("[green]Created .env template[/green]")

    console.print(Panel(
        "[bold green]LinkedIn Agent initialized![/bold green]\n\n"
        "Next steps:\n"
        "  1. Edit linkedin_config.yaml with your settings\n"
        "  2. Edit .env with your credentials\n"
        "  3. Place your resume.pdf in the project root\n"
        "  4. Run: python -m src.linked_agent.main run",
        title="Setup Complete",
        border_style="green",
    ))


@cli.command("verify-application")
@click.argument("job_id")
def verify_application(job_id: str) -> None:
    """Inspect an uncertain application's saved account without submitting anything."""
    import re
    if not re.fullmatch(r"\d{6,20}", job_id):
        raise click.BadParameter("Use the numeric LinkedIn job ID.")

    async def _verify():
        import contextlib
        import json
        from src.linked_agent.config.settings import get_settings
        from src.linked_agent.bot.factory import LinkedInDependencyFactory
        from src.linked_agent.browser.navigation import navigate

        settings = get_settings()
        factory = LinkedInDependencyFactory(settings)
        engine = factory.get_browser_engine()
        try:
            page = await engine.launch()
            if not await factory.create_login_handler().login():
                raise click.ClickException("LinkedIn sign-in requires attention.")
            await navigate(page, f"https://www.linkedin.com/jobs/view/{job_id}/")
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=10000)
            await asyncio.sleep(3)
            result = await page.evaluate(r"""() => {
                const scope = document.querySelector('section[aria-label="Primary content"], main') || document.body;
                const text = (scope.innerText || '').split(/About the job/i)[0].slice(0,1800);
                const visible = el => el.getClientRects().length && !el.closest('[inert],[hidden]');
                return {appliedSignals: text.split('\n').filter(t => /^\s*(?:Applied\b|Application (?:sent|submitted)\b|You applied\b)/i.test(t)).map(t=>t.trim()),
                    applyControls: [...scope.querySelectorAll('button,a')].filter(visible).map(el=>(el.innerText || el.getAttribute('aria-label') || '').trim()).filter(t=>/^(?:Easy Apply|Apply|Applied|View application)(?:$| to )/i.test(t))};
            }""")
            from src.linked_agent.browser.receipts import inline_submission_confirmed
            result['confirmed'] = await inline_submission_confirmed(page, job_id)
            folder = settings.project_root / "data" / "linkedin"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"verification_{job_id}.png"
            await page.screenshot(path=str(path))
            console.print(json.dumps({"job_id": job_id, **result, "screenshot": str(path)}))
        finally:
            await engine.close()

    _run_async(_verify())


if __name__ == "__main__":
    cli()
