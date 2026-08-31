"""Additional tests for database repository to increase coverage."""

import pytest
from unittest.mock import AsyncMock, MagicMock


def test_repository_initialization():
    """Test repository initialization."""
    from src.naukri_agent.database.repository import SQLAlchemyRepository
    
    mock_db_manager = AsyncMock()
    repo = SQLAlchemyRepository(mock_db_manager)
    
    assert repo is not None
    # The db_manager is stored as _db_manager (private attribute)
    assert hasattr(repo, '_db_manager')


def test_repository_initialize_method():
    """Test repository initialize method."""
    from src.naukri_agent.database.repository import SQLAlchemyRepository
    
    mock_db_manager = AsyncMock()
    repo = SQLAlchemyRepository(mock_db_manager)
    
    # Test initialize method exists
    assert hasattr(repo, 'initialize')
    assert callable(repo.initialize)