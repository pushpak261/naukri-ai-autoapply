"""Tests for logging setup, the PII scrubber, and the console helpers."""

import logging
from pathlib import Path

import pytest

from src.naukri_agent.utils import logger as logger_mod
from src.naukri_agent.utils.logger import (
    PIIScrubberFilter,
    log_error,
    log_info,
    log_match,
    log_step,
    log_success,
    log_warning,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """Undo every mutation these tests make to the global logging state."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_configured = logger_mod._configured
    yield
    for handler in list(root.handlers):
        if handler not in original_handlers:
            root.removeHandler(handler)
            handler.close()
    root.handlers[:] = original_handlers
    root.setLevel(original_level)
    logger_mod._configured = original_configured


def _record(msg: object, name: str = "test") -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, __file__, 1, msg, None, None)


class TestPIIScrubberFilter:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("contact me at jane.doe+tag@example.co.uk now", "contact me at [EMAIL] now"),
            ("password=hunter2", "password=***"),
            ("pwd: hunter2", "pwd=***"),
            ("api_key = sk-abc123", "api_key=***"),
            ("token=zzz999", "token=***"),
            ("key AIzaSyA1234567890abcdefghijklmnopqrstuv", "key [GEMINI_API_KEY]"),
        ],
    )
    def test_scrubs_secrets(self, raw, expected):
        record = _record(raw)

        assert PIIScrubberFilter().filter(record) is True
        assert record.msg == expected

    def test_scrubs_every_match_in_one_message(self):
        record = _record("a@b.com and password=letmein")

        PIIScrubberFilter().filter(record)

        assert "[EMAIL]" in record.msg
        assert "***" in record.msg

    def test_leaves_ordinary_messages_intact(self):
        record = _record("Applied to Senior Engineer at Acme")

        PIIScrubberFilter().filter(record)

        assert record.msg == "Applied to Senior Engineer at Acme"

    def test_ignores_non_string_messages(self):
        """Lazy %-style formatting must not crash the filter."""
        record = _record(12345)

        assert PIIScrubberFilter().filter(record) is True
        assert record.msg == 12345


class TestSetupLogging:
    def test_configures_console_handler(self):
        setup_logging(log_to_file=False)

        root = logging.getLogger()
        assert root.level == logging.INFO
        assert any(type(h).__name__ == "RichHandler" for h in root.handlers)

    def test_parses_explicit_level(self):
        setup_logging(level="WARNING", log_to_file=False)

        assert logging.getLogger().level == logging.WARNING

    def test_unknown_level_falls_back_to_info(self):
        setup_logging(level="not-a-level", log_to_file=False)

        assert logging.getLogger().level == logging.INFO

    def test_adds_file_handler_and_creates_directory(self, tmp_path):
        log_dir = tmp_path / "nested" / "logs"

        setup_logging(level="DEBUG", log_to_file=True, log_dir=str(log_dir))

        assert log_dir.exists()
        # Ignore pytest's own NUL-capture handler, which is also a FileHandler.
        file_handlers = [
            h
            for h in logging.getLogger().handlers
            if isinstance(h, logging.FileHandler) and Path(h.baseFilename).parent == log_dir
        ]
        assert file_handlers, "expected a FileHandler writing into log_dir"
        assert file_handlers[0].level == logging.DEBUG
        assert file_handlers[0].formatter is not None

    def test_is_idempotent(self, tmp_path):
        setup_logging(log_to_file=False)
        before = len(logging.getLogger().handlers)

        setup_logging(log_to_file=False)  # _configured short-circuits

        assert len(logging.getLogger().handlers) == before

    def test_file_handler_scrubs_pii(self, tmp_path):
        log_dir = tmp_path / "logs"
        setup_logging(log_to_file=True, log_dir=str(log_dir))

        record = _record("password=leaked")
        record.levelname = "INFO"
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.handle(record)

        log_file = next(log_dir.glob("agent_*.log"))
        content = log_file.read_text(encoding="utf-8")
        assert "leaked" not in content
        assert "***" in content


class TestConsoleHelpers:
    @pytest.mark.parametrize(
        ("fn", "prefix"),
        [(log_info, "ℹ️"), (log_success, "✅"), (log_warning, "⚠️"), (log_error, "❌")],
    )
    def test_prints_expected_prefix(self, fn, prefix, capsys):
        fn("hello")

        assert prefix in capsys.readouterr().out

    @pytest.mark.parametrize(
        "fn", [log_info, log_success, log_warning, log_error]
    )
    def test_forged_newlines_cannot_create_extra_lines(self, fn, capsys):
        fn("legit line\nFAKE | ERROR | forged record")

        out = capsys.readouterr().out
        # The payload keeps its text but is flattened onto exactly one line.
        assert out.count("\n") == 1
        assert "legit line FAKE | ERROR | forged record" in out

    def test_error_uses_error_level(self, caplog):
        with caplog.at_level(logging.ERROR):
            log_error("boom")

        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_warning_uses_warning_level(self, caplog):
        with caplog.at_level(logging.WARNING):
            log_warning("careful")

        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_step_shows_progress(self, capsys):
        log_step(3, 10, "Applying to job")

        out = capsys.readouterr().out
        assert "[3/10]" in out
        assert "Applying to job" in out

    def test_step_sanitizes_message(self, capsys):
        log_step(1, 2, "start\ninjected")

        out = capsys.readouterr().out
        assert out.count("\n") == 1
        assert "[1/2] start injected" in out


class TestLogMatch:
    @pytest.mark.parametrize(
        ("score", "expected_style", "emoji"),
        [
            (95, "success", "🟢"),
            (80, "success", "🟢"),
            (75, "warning", "🟡"),
            (60, "warning", "🟡"),
            (42, "error", "🔴"),
            (0, "error", "🔴"),
        ],
    )
    def test_color_coding_follows_score(self, score, expected_style, emoji, capsys):
        log_match(score, "Dev", "Acme")

        out = capsys.readouterr().out
        assert emoji in out
        assert f"Score: {score:.0f}/100" in out

    def test_apply_decision_is_shown_when_supplied(self, capsys):
        log_match(95, "Dev", "Acme", should_apply=True)

        assert "APPLY" in capsys.readouterr().out

    def test_skip_decision_is_shown(self, capsys):
        log_match(95, "Dev", "Acme", should_apply=False)

        assert "skip" in capsys.readouterr().out

    def test_no_decision_suffix_when_none(self, capsys):
        log_match(95, "Dev", "Acme", should_apply=None)

        out = capsys.readouterr().out
        assert "APPLY" not in out
        assert "skip" not in out
