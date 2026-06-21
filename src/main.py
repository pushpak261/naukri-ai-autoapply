"""
CLI entry point for the Naukri.com AI Job Application Agent.

Provides subcommands for running the agent, viewing status, parsing
resumes, and testing job matching.

Usage:
    python -m src.main run [--dry-run]
    python -m src.main status
    python -m src.main parse-resume <path>
    python -m src.main test-match <job_url>
"""

from __future__ import annotations

import asyncio

import click

from src.config.settings import get_settings
from src.utils.logger import console


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
    asyncio.run(_run(dry_run, cap, threshold))


async def _run(dry_run: bool, cap: int | None, threshold: int | None):
    from src.orchestrator.agent import NaukriAgent
    from src.orchestrator.factory import DependencyFactory
    from src.database.models import init_db

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
    factory = DependencyFactory(settings, session_factory=session_factory)
    agent = NaukriAgent(factory)
    await agent.run(dry_run=dry_run)


@cli.command()
def status():
    """Show application statistics and recent history."""
    asyncio.run(_status())


async def _status():
    from src.orchestrator.agent import NaukriAgent
    from src.orchestrator.factory import DependencyFactory
    from src.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    factory = DependencyFactory(settings, session_factory=session_factory)
    agent = NaukriAgent(factory)
    await agent.show_status()


@cli.command("parse-resume")
@click.argument("resume_path", type=click.Path(exists=True))
def parse_resume(resume_path: str):
    """Parse a resume PDF and display the structured profile."""
    asyncio.run(_parse_resume(resume_path))


async def _parse_resume(resume_path: str):
    from src.orchestrator.agent import NaukriAgent
    from src.orchestrator.factory import DependencyFactory
    from src.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    factory = DependencyFactory(settings, session_factory=session_factory)
    agent = NaukriAgent(factory)
    await agent.parse_resume_only(resume_path)


@cli.command("test-match")
@click.argument("job_url")
def test_match(job_url: str):
    """Test job matching against a specific Naukri job URL."""
    asyncio.run(_test_match(job_url))


async def _test_match(job_url: str):
    from src.orchestrator.agent import NaukriAgent
    from src.orchestrator.factory import DependencyFactory
    from src.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    factory = DependencyFactory(settings, session_factory=session_factory)
    agent = NaukriAgent(factory)
    await agent.test_match(job_url)


@cli.command("refresh-profile")
def refresh_profile():
    """Automated task to refresh the user profile."""
    asyncio.run(_refresh_profile())


async def _refresh_profile():
    from src.orchestrator.agent import NaukriAgent
    from src.orchestrator.factory import DependencyFactory
    from src.database.models import init_db

    settings = get_settings()
    session_factory = await init_db(settings.db_path)
    factory = DependencyFactory(settings, session_factory=session_factory)
    agent = NaukriAgent(factory)
    await agent.refresh_profile()


@cli.command()
def init():
    """Initialize configuration files and data directories."""
    import shutil

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

    console.print("  ✅ Data directories created")
    console.print()
    console.print("[bold cyan]Next steps:[/bold cyan]")
    console.print("  1. Edit [bold].env[/bold] with your Naukri credentials and Gemini API key")
    console.print("  2. Edit [bold]config.yaml[/bold] with your job preferences")
    console.print("  3. Run [bold]python -m src.main run --dry-run[/bold] to test")


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
