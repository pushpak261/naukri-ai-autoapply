import sys
import re
import threading
from pathlib import Path
from datetime import datetime

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from text."""
    return ANSI_ESCAPE.sub("", text)


class DualStream:
    """A stream that writes to both an original stream (stdout/stderr) and a log file."""

    def __init__(self, original_stream, log_file, lock: threading.Lock):
        self.original_stream = original_stream
        self.log_file = log_file
        self.lock = lock

    def write(self, data: str) -> int:
        # Write to original stream first
        written = self.original_stream.write(data)

        # Write clean data to log file
        clean_data = strip_ansi(data)
        if clean_data:
            with self.lock:
                self.log_file.write(clean_data)
                self.log_file.flush()

        # Flush original stream if data contains a newline.
        # This ensures real-time delivery through the pipe to the API's reader thread.
        # Without this, Python's block buffering (default for non-TTY / pipe)
        # would hold output in the child process's stdio buffer indefinitely.
        if "\n" in data:
            self.original_stream.flush()

        return written

    def flush(self) -> None:
        self.original_stream.flush()
        with self.lock:
            self.log_file.flush()

    def isatty(self) -> bool:
        return getattr(self.original_stream, "isatty", lambda: False)()

    @property
    def encoding(self) -> str:
        return getattr(self.original_stream, "encoding", "utf-8")

    @property
    def errors(self) -> str:
        return getattr(self.original_stream, "errors", "strict")

    def __getattr__(self, attr):
        return getattr(self.original_stream, attr)


def setup_terminal_logging() -> None:
    """Set up redirection of stdout and stderr to a timestamped file in terminal_output/."""
    # Determine directory
    output_dir = Path("terminal_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = output_dir / f"terminal_{timestamp}.log"

    # Open file with utf-8 encoding and replace errors to be robust
    log_file = open(log_file_path, "a", encoding="utf-8", errors="replace")

    lock = threading.Lock()

    # Wrap sys.stdout and sys.stderr
    sys.stdout = DualStream(sys.stdout, log_file, lock)
    sys.stderr = DualStream(sys.stderr, log_file, lock)

    # Update Rich console so it writes through the new DualStream wrapper.
    # logger.py creates its module-level Console() object at import time,
    # which captures sys.stdout *before* this function wraps it. Without
    # this update, all console.print() calls bypass DualStream and write
    # directly to the block-buffered pipe, never reaching the parent process.
    try:
        from src.naukri_agent.utils.logger import console

        console._file = sys.stdout
    except (ImportError, AttributeError):
        pass
