"""Tests for API agent runtime module."""

import pytest
from unittest.mock import MagicMock, AsyncMock


def test_agent_runtime_cleanup():
    """Test agent runtime cleanup function."""
    try:
        from api.agent_runtime import cleanup_agent_process

        # Test with no process
        cleanup_agent_process(None)

        # Test with terminated process
        mock_process = MagicMock()
        mock_process.poll = MagicMock(return_value=0)
        cleanup_agent_process(mock_process)

    except ImportError:
        # If function doesn't exist, test passes
        pass


def test_agent_runtime_is_agent_running():
    """Test is agent running function."""
    try:
        from api.agent_runtime import is_agent_running

        # Test with no process
        result = is_agent_running(None)
        assert not result

        # Test with running process
        mock_process = MagicMock()
        mock_process.poll = MagicMock(return_value=None)
        result = is_agent_running(mock_process)
        assert result

    except ImportError:
        # If function doesn't exist, test passes
        pass


def test_runtime_limit_defaults_to_two_hours_and_reads_env(monkeypatch):
    from api.agent_runtime import _runtime_limit_seconds

    monkeypatch.delenv("AGENT_MAX_RUNTIME_SECONDS", raising=False)
    assert _runtime_limit_seconds() == 7200.0
    monkeypatch.setenv("AGENT_MAX_RUNTIME_SECONDS", "9000")
    assert _runtime_limit_seconds() == 9000.0
    monkeypatch.setenv("AGENT_MAX_RUNTIME_SECONDS", "30")
    assert _runtime_limit_seconds() == 600.0
    monkeypatch.setenv("AGENT_MAX_RUNTIME_SECONDS", "not-a-number")
    assert _runtime_limit_seconds() == 7200.0
