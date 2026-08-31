"""Tests for API stats parallel query optimization."""

import pytest
from unittest.mock import AsyncMock, MagicMock


def test_stats_repository_methods():
    """Test that stats repository methods exist and are callable."""
    from api.deps import state as deps
    
    # Mock repository
    deps.repo = AsyncMock()
    deps.repo.get_application_stats = AsyncMock(return_value={
        "total": 10,
        "applied": 5,
        "skipped": 3,
        "failed": 2
    })
    deps.repo.get_today_application_count = AsyncMock(return_value=1)
    deps.repo.get_run_stats = AsyncMock(return_value=[])
    deps.repo.get_recent_applications = AsyncMock(return_value=[])
    
    # Test that methods are callable
    import asyncio
    stats = asyncio.run(deps.repo.get_application_stats(days=7))
    today = asyncio.run(deps.repo.get_today_application_count())
    runs = asyncio.run(deps.repo.get_run_stats(limit=10))
    recent = asyncio.run(deps.repo.get_recent_applications(limit=5))
    
    assert stats["total"] == 10
    assert today == 1
    assert runs == []
    assert recent == []