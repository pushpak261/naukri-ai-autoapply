"""
Structured logging for the Naukri Agent using Python's logging + Rich.

Provides color-coded console output with emoji indicators and optional
file logging to data/logs/agent_YYYY-MM-DD.log.
"""

from __future__ import annotations

import logging
import sys
import re
from datetime import datetime
from pathlib import Path
import contextlib

# Force UTF-8 encoding for stdout on Windows to prevent emoji UnicodeEncodeError
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")


from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Custom Rich theme
# ---------------------------------------------------------------------------
AGENT_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "highlight": "bold magenta",
        "dim": "dim white",
    }
)

console = Console(theme=AGENT_THEME)

# ---------------------------------------------------------------------------
# Module-level logger cache and Filters
# ---------------------------------------------------------------------------
_configured = False


class PIIScrubberFilter(logging.Filter):
    """Filter to scrub PII (emails, passwords, API keys) from logs."""

    def __init__(self):
        super().__init__()
        self.patterns = [
            (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[EMAIL]"),
            (re.compile(r"(?i)(password|passwd|pwd)[\s:=]+[^\s]+"), r"\1=***"),
            (re.compile(r"(?i)(api_key|apikey|token)[\s:=]+[^\s]+"), r"\1=***"),
            (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[GEMINI_API_KEY]"),
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self.patterns:
                record.msg = pattern.sub(replacement, record.msg)
        return True


def setup_logging(
    level: str = "INFO", log_to_file: bool = True, log_dir: str = "data/logs"
) -> None:
    """
    Configure the root logger with Rich console handler and optional file handler.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR).
        log_to_file: Whether to also log to a file.
        log_dir: Directory for log files.
    """
    global _configured
    if _configured:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Rich console handler (pretty output)
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        log_time_format="[%H:%M:%S]",
    )
    rich_handler.setLevel(log_level)

    pii_filter = PIIScrubberFilter()
    rich_handler.addFilter(pii_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(rich_handler)

    # File handler (if enabled)
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        file_handler = logging.FileHandler(
            log_path / f"agent_{today}.log",
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # Always DEBUG for file
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(pii_filter)
        root_logger.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A configured Logger instance.
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Convenience emoji-prefixed log methods for the console
# ---------------------------------------------------------------------------
def log_info(message: str) -> None:
    """Log an info message with a ℹ️ prefix."""
    console.print(f"  ℹ️  {message}", style="info")


def log_success(message: str) -> None:
    """Log a success message with a ✅ prefix."""
    console.print(f"  ✅ {message}", style="success")


def log_warning(message: str) -> None:
    """Log a warning message with a ⚠️ prefix."""
    console.print(f"  ⚠️  {message}", style="warning")


def log_error(message: str) -> None:
    """Log an error message with a ❌ prefix."""
    console.print(f"  ❌ {message}", style="error")


def log_step(step_num: int, total: int, message: str) -> None:
    """Log a progress step like '  [3/10] Applying to job...'."""
    console.print(f"  [{step_num}/{total}] {message}", style="highlight")


def log_match(
    score: float,
    title: str,
    company: str,
    should_apply: bool | None = None,
) -> None:
    """
    Log a match score result with color coding.

    Args:
        score: The AI match score (0-100).
        title: Job title.
        company: Company name.
        should_apply: Optional flag indicating whether the score cleared the
            configured threshold. Purely informational — does not affect the
            color coding, which is always derived from the score itself.
    """
    if score >= 80:
        style = "success"
        emoji = "🟢"
    elif score >= 60:
        style = "warning"
        emoji = "🟡"
    else:
        style = "error"
        emoji = "🔴"

    suffix = ""
    if should_apply is not None:
        suffix = "  [bold]→ APPLY[/bold]" if should_apply else "  → skip"

    console.print(
        f"  {emoji} Score: {score:.0f}/100 — {title} @ {company}{suffix}",
        style=style,
    )
