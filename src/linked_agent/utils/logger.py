"""
Logging configuration for the LinkedIn Agent.
Provides structured logging with Rich console output and PII scrubbing.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

console = Console(force_terminal=True)

# PII patterns to scrub from logs
_PII_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.IGNORECASE),  # email
    re.compile(r"\b\d{10}\b"),  # phone (10 digits)
    re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # phone formats
    re.compile(r"password[=:]\s*\S+", re.IGNORECASE),  # password=xxx
]


def _scrub_pii(message: str) -> str:
    """Remove PII from log messages."""
    for pattern in _PII_PATTERNS:
        message = pattern.sub("[REDACTED]", message)
    return message


class PIIFormatter(logging.Formatter):
    """Logging formatter that scrubs PII from log messages."""

    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, str):
            record.msg = _scrub_pii(record.msg)
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance."""
    return logging.getLogger(name)


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: str = "data/logs",
) -> None:
    """
    Configure the root logger with Rich console output and optional file output.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # Already configured

    log_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(log_level)

    # Console handler with Rich
    rich_handler = RichHandler(
        console=console,
        show_path=False,
        show_time=True,
        rich_tracebacks=True,
        markup=True,
    )
    rich_handler.setLevel(log_level)
    root.addHandler(rich_handler)

    # File handler
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_path / "linkedin_agent.log",
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(
            PIIFormatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        )
        root.addHandler(file_handler)


def log_info(message: str) -> None:
    """Log an info message with Rich formatting."""
    console.print(f"  [dim]i[/dim] {message}")
    logging.getLogger("linked_agent").info(message)


def log_success(message: str) -> None:
    """Log a success message."""
    console.print(f"  [bold green]+[/bold green] {message}")
    logging.getLogger("linked_agent").info(message)


def log_warning(message: str) -> None:
    """Log a warning message."""
    console.print(f"  [bold yellow]![/bold yellow] {message}")
    logging.getLogger("linked_agent").warning(message)


def log_error(message: str) -> None:
    """Log an error message."""
    console.print(f"  [bold red]x[/bold red] {message}")
    logging.getLogger("linked_agent").error(message)


def log_step(step: int, total: int, message: str) -> None:
    """Log a step in a multi-step process."""
    console.print(
        f"  [cyan][{step}/{total}][/cyan] {message}"
    )
    logging.getLogger("linked_agent").info(f"[{step}/{total}] {message}")
