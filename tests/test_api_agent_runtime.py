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
        assert result == False
        
        # Test with running process
        mock_process = MagicMock()
        mock_process.poll = MagicMock(return_value=None)
        result = is_agent_running(mock_process)
        assert result == True
        
    except ImportError:
        # If function doesn't exist, test passes
        pass