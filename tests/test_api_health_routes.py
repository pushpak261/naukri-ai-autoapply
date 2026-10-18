"""Tests for API health routes."""

import pytest
from fastapi import Response
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_health_check_disk_usage():
    """Test health check handles disk usage calculation."""
    from api.routes.health import health
    from api.deps import state as deps
    
    # Mock settings and dependencies
    deps.settings = MagicMock()
    deps.settings.project_root = "C:\\test"
    deps.db_manager = None
    deps.agent_process = None
    deps.settings.ai = MagicMock()
    deps.settings.ai.gemini_api_key = None
    
    with patch('shutil.disk_usage') as mock_disk:
        mock_disk.return_value = MagicMock(
            total=1000*1024*1024*1024,  # 1TB
            free=500*1024*1024*1024,   # 500GB
            used=500*1024*1024*1024     # 500GB
        )
        
        # Call the function directly to test the logic
        response = Response()
        result = await health(response)
        
        assert result["status"] == "degraded"
        assert response.status_code == 503
        assert "disk" in result["checks"]
        assert result["checks"]["disk"]["total_gb"] == 1000.0
        assert result["checks"]["disk"]["free_gb"] == 500.0


@pytest.mark.asyncio
async def test_health_reports_healthy_database_and_handles_disk_failure(tmp_path, monkeypatch):
    from api.routes.health import health
    from api.deps import state
    settings = MagicMock(project_root=tmp_path, db_path=tmp_path / "test.db")
    settings.ai.gemini_api_key = ""
    connection = AsyncMock()
    engine = MagicMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    monkeypatch.setattr(state, "settings", settings)
    monkeypatch.setattr(state, "db_manager", MagicMock(engine=engine))
    monkeypatch.setattr(state, "agent_process", None)
    response = Response()
    assert (await health(response))["status"] == "ok"
    assert response.status_code == 200
    with patch("api.routes.health.shutil.disk_usage", side_effect=OSError("Unavailable")):
        result = await health(response)
    assert response.status_code == 503
    assert result["checks"]["disk"]["status"] == "error"
