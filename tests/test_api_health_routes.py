"""Tests for API health routes."""

import pytest
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
        result = await health()
        
        assert result["status"] == "ok"
        assert "disk" in result["checks"]
        assert result["checks"]["disk"]["total_gb"] == 1000.0
        assert result["checks"]["disk"]["free_gb"] == 500.0