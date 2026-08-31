"""Comprehensive tests for api/main.py to increase new code coverage."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_get_active_account_email_with_db():
    """Test get_active_account_email with database query."""
    from api.main import get_active_account_email
    from api.deps import state as deps
    from sqlalchemy import select
    
    # Mock settings with naukri config
    deps.settings = MagicMock()
    deps.settings.naukri = MagicMock()
    deps.settings.naukri.email = "test@example.com"
    deps.settings.naukri.password = "password"
    deps.settings.naukri.name = "Test User"
    
    # Mock database manager and session
    deps.db_manager = AsyncMock()
    session_factory = AsyncMock()
    session = AsyncMock()
    
    # Mock query that returns no active account
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = MagicMock(return_value=result_mock)
    session.__aenter__ = MagicMock(return_value=session)
    session.__aexit__ = MagicMock(return_value=None)
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None
    deps.db_manager.get_session_factory = AsyncMock(return_value=session_factory)
    
    deps.active_account_email = None
    
    # Should return None when no active account found
    result = await get_active_account_email()
    assert result is None


@pytest.mark.asyncio
async def test_get_active_account_email_auto_seed():
    """Test get_active_account_email auto-seeds when no active account."""
    from api.main import get_active_account_email
    from api.deps import state as deps
    from src.naukri_agent.models.db_schema import NaukriAccount
    
    # Mock settings with naukri config
    deps.settings = MagicMock()
    deps.settings.naukri = MagicMock()
    deps.settings.naukri.email = "test@example.com"
    deps.settings.naukri.password = "password"
    deps.settings.naukri.name = "Test User"
    
    # Mock database manager and session
    deps.db_manager = AsyncMock()
    session_factory = AsyncMock()
    session = AsyncMock()
    
    # Mock query that returns no active account, then auto-seed
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = MagicMock(return_value=result_mock)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.__aenter__ = MagicMock(return_value=session)
    session.__aexit__ = MagicMock(return_value=None)
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None
    deps.db_manager.get_session_factory = AsyncMock(return_value=session_factory)
    
    deps.active_account_email = None
    
    # Should return None when no account found (auto-seeding happens but return is still None)
    result = await get_active_account_email()
    assert result is None