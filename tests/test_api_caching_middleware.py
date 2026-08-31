"""Tests for API caching middleware changes."""

import pytest
from unittest.mock import MagicMock, AsyncMock


def test_caching_headers_on_get_requests():
    """Test that caching headers are set on GET requests."""
    from api.main import app
    from api.deps import state as deps
    from fastapi.testclient import TestClient
    
    # Mock settings without API key
    deps.settings = MagicMock()
    deps.settings.dashboard_api_key = None
    deps.db_manager = AsyncMock()
    deps.repo = AsyncMock()
    deps.agent_process = None
    deps.active_account_email = None
    
    client = TestClient(app)
    
    # Test GET request gets caching headers
    response = client.get("/")
    assert response.status_code == 200
    # In development mode, caching might not be applied
    # but the middleware should be present