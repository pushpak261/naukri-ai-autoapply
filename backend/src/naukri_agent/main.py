"""
CLI entry point for the Naukri.com AI Job Application Agent.

Provides subcommands for running the agent, viewing status, parsing
resumes, and testing job matching.

Usage:
    python -m src.naukri_agent.main run [--dry-run]
    python -m src.naukri_agent.main status
    python -m src.naukri_agent.main parse-resume <path>
    python -m src.naukri_agent.main test-match <job_url>
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

import click

from src.naukri_agent.config.settings import get_settings
from src.naukri_agent.utils.logger import console, get_logger

if TYPE_CHECKING:
    from src.naukri_agent.orchestrator.agent import NaukriAgent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Alert helpers
# ---------------------------------------------------------------------------
def _create_notifier(settings):
    """Construct an ``EmailAlertNotifier`` from the current settings.

    Returns ``None`` when alerts are disabled or SMTP credentials are
    missing — callers must handle a ``None`` return.
    """
    if not settings.alerts.enabled:
        return None

    sender = settings.naukri.gmail_otp_email
    password = settings.naukri.gmail_app_password
    if not sender or not password:
        return None

    from src.naukri_agent.utils.email_notifier import EmailAlertNotifier

    return EmailAlertNotifier(
        sender_email=sender,
        app_password=password,
        recipient_email=settings.alerts.recipient_email,
        cooldown_minutes=settings.alerts.cooldown_minutes,
        cooldown_dir=str(settings.project_root / settings.logging.log_dir),
    )


async def _run_with_alerts(task_name: str, coro: Coroutine[Any, Any, Any]) -> Any:
    """Run *coro* and send an email alert if it raises an exception.

    The exception is always re-raised so existing error handling (log +
    exit code) continues to work as before.
    """
    try:
        return await coro
    except (SystemExit, KeyboardInterrupt):
        raise  # Never alert on intentional exits
    except Exception as exc:
        # Best-effort alert — must not mask the original error
        try:
            settings = get_settings()
            notifier = _create_notifier(settings)
            if notifier:
                await notifier.send_alert(task_name, exc)
        except Exception as alert_err:
            logger.warning(f"Could not send failure alert: {alert_err}")
        raise


@click.group()
@click.version_option(version="1.0.0", prog_name="Naukri AI Agent")
def cli():
    """🤖 Naukri.com AI-Powered Job Application Agent"""
    pass


@cli.command()
@click.option("--dry-run", is_flag=True, help="Score jobs without actually applying")
@click.option(
    "--cap",
    type=int,
    default=None,
    help="Override daily application cap",
)
@click.option(
    "--threshold",
    type=int,
    default=None,
    help="Override minimum match score threshold (0-100)",
)
def run(dry_run: bool, cap: int | None, threshold: int | None):
    """Start the job application agent."""
    asyncio.run(_run_with_alerts("run", _run(dry_run, cap, threshold)))


def create_agent(settings, session_factory, progress_reporter=None) -> NaukriAgent:
    from src.naukri_agent.orchestrator.agent import NaukriAgent
    from src.naukri_agent.orchestrator.factory import DependencyFactory

    factory = DependencyFactory(settings, session_factory=session_factory)
    return NaukriAgent(
        settings=factory.get_settings(),
        repository=factory.get_repository(),
        browser_engine=factory.get_browser_engine(),
        browser_interactions=factory.get_browser_interactions(),
        llm_provider=factory.get_llm_provider(),
        resume_parser=factory.create_resume_parser(),
        login_handler=factory.create_login_handler(),
        job_searcher=factory.create_job_searcher(),
        job_matcher=factory.create_job_matcher(),
        question_answerer_factory=lambda profile: factory.create_question_answerer(profile),
        job_applier_factory=lambda qa: factory.create_job_applier(qa),
        profile_refresher=factory.create_profile_refresher(),
        progress_reporter=progress_reporter,
    )


async def _run(dry_run: bool, cap: int | None, threshold: int | None):
    from src.naukri_agent.database.models import init_db

    settings = get_settings()

    # Apply CLI overrides
    if cap is not None:
        settings.application.daily_cap = cap
    if threshold is not None:
        settings.application.match_score_threshold = threshold

    problems = settings.validate_required()
    if problems:
        console.print("[bold red]Configuration error — cannot start the agent:[/bold red]")
        for problem in problems:
            console.print(f"  • {problem}")
        console.print("\n[dim]See .env.example and config.yaml for what needs to be set.[/dim]")
        raise SystemExit(1)

    session_factory = await init_db(settings.db_path)
    agent = create_agent(settings, session_factory)
    await agent.run(dry_run=dry_run)


@cli.command()
def status():
    """Show application statistics and recent history."""
    asyncio.run(_run_with_alerts("status", _status()))


async def _status():
    from src.naukri_agent.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    agent = create_agent(settings, session_factory)
    await agent.show_status()


@cli.command("parse-resume")
@click.argument("resume_path", type=click.Path(exists=True))
def parse_resume(resume_path: str):
    """Parse a resume PDF and display the structured profile."""
    asyncio.run(_run_with_alerts("parse-resume", _parse_resume(resume_path)))


async def _parse_resume(resume_path: str):
    from src.naukri_agent.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    agent = create_agent(settings, session_factory)
    await agent.parse_resume_only(resume_path)


@cli.command("test-match")
@click.argument("job_url")
def test_match(job_url: str):
    """Test job matching against a specific Naukri job URL."""
    asyncio.run(_run_with_alerts("test-match", _test_match(job_url)))


async def _test_match(job_url: str):
    from src.naukri_agent.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    agent = create_agent(settings, session_factory)
    await agent.test_match(job_url)


@cli.command("refresh-profile")
def refresh_profile():
    """Automated task to refresh the user profile."""
    asyncio.run(_run_with_alerts("refresh-profile", _refresh_profile()))


async def _refresh_profile():
    from src.naukri_agent.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    agent = create_agent(settings, session_factory)
    await agent.refresh_profile()


@cli.command()
def init():
    """Initialize configuration files and data directories."""
    import shutil

    from src.naukri_agent.utils.secrets import decrypt_local_secrets

    settings = get_settings()
    settings.ensure_dirs()

    # Check for .env
    env_path = settings.project_root / ".env"
    env_example = settings.project_root / ".env.example"

    if not env_path.exists() and env_example.exists():
        shutil.copy(env_example, env_path)
        console.print("  ✅ Created .env file from .env.example")
        console.print("  📝 Please edit .env and fill in your credentials")
    elif env_path.exists():
        console.print("  ℹ️  .env already exists")

    decrypt_messages = decrypt_local_secrets(settings.project_root)
    if decrypt_messages:
        console.print("  🔐 Encrypted assets:")
        for message in decrypt_messages:
            if message.startswith("No decryption key"):
                console.print(f"  ℹ️  {message}")
            elif "Could not decrypt" in message:
                console.print(f"  ⚠️  {message}")
            elif message.startswith("Skipped"):
                console.print(f"  ℹ️  {message}")
            else:
                console.print(f"  ✅ {message}")

    resume_path = settings.project_root / settings.resume.path
    if not resume_path.exists():
        console.print(
            "  ⚠️  resume.pdf is missing — add it to the backend directory, or run "
            "[bold]python scripts/decrypt_secrets.py[/bold] if you have resume_key.txt"
        )
    else:
        console.print("  ✅ Resume file found")

    console.print("  ✅ Data directories created")
    console.print()
    console.print("[bold cyan]Next steps:[/bold cyan]")
    console.print("  1. Edit [bold].env[/bold] with your Naukri credentials and Gemini API key")
    console.print("  2. Edit [bold]config.yaml[/bold] with your job preferences")
    console.print("  3. Run [bold]python -m src.naukri_agent.main run --dry-run[/bold] to test")


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
