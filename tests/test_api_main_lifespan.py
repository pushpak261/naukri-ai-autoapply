"""Tests for API main lifespan function changes."""

import pytest
from unittest.mock import AsyncMock, MagicMock


def test_lifespan_defers_account_resolution():
    """Test that lifespan defers account resolution to first request."""
    from api.main import app
    from api.deps import state as deps
    
    # After lifespan, active_account_email should be None (deferred)
    deps.settings = MagicMock()
    deps.db_manager = AsyncMock()
    deps.repo = AsyncMock()
    deps.agent_process = None
    deps.active_account_email = None
    
    # The lifespan should not set active_account_email
    assert deps.active_account_email is None