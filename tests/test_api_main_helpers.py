"""Tests for API main helper functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_get_active_account_email_no_state():
    """Test get_active_account_email when no state is set."""
    from api.main import get_active_account_email
    from api.deps import state as deps
    
    deps.active_account_email = None
    deps.settings = None
    deps.db_manager = None
    
    result = await get_active_account_email()
    assert result is None


@pytest.mark.asyncio
async def test_get_active_account_email_cached():
    """Test get_active_account_email when already cached."""
    from api.main import get_active_account_email
    from api.deps import state as deps
    
    deps.active_account_email = "test@example.com"
    deps.settings = None
    deps.db_manager = None
    
    result = await get_active_account_email()
    assert result == "test@example.com"


def test_cleanup_agent_no_process():
    """Test _cleanup_agent when no process is running."""
    from api.main import _cleanup_agent
    from api.deps import state as deps
    
    deps.agent_process = None
    _cleanup_agent()  # Should not raise


def test_cleanup_agent_terminated_process():
    """Test _cleanup_agent when process is already terminated."""
    from api.main import _cleanup_agent
    from api.deps import state as deps
    from unittest.mock import MagicMock
    
    mock_process = MagicMock()
    mock_process.poll = MagicMock(return_value=0)  # Already terminated
    deps.agent_process = mock_process
    
    _cleanup_agent()  # Should not raise


def test_cleanup_agent_running_process():
    """Test _cleanup_agent when process is running."""
    from api.main import _cleanup_agent
    from api.deps import state as deps
    from unittest.mock import MagicMock
    
    mock_process = MagicMock()
    mock_process.poll = MagicMock(return_value=None)  # Still running
    mock_process.terminate = MagicMock()
    mock_process.wait = MagicMock(return_value=0)
    deps.agent_process = mock_process
    
    _cleanup_agent()
    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_called_once()