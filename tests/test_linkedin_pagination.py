"""
Unit tests for LinkedIn search pagination and empty results detection.
"""

import math
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.linked_agent.browser.pages.search import LinkedInSearchPage
from src.linked_agent.config.constants import SearchSelectors


@pytest.fixture
def mock_engine():
    """Mock BrowserEngine."""
    engine = MagicMock()
    engine.page = AsyncMock()
    return engine


def test_no_results_selector_patterns():
    """Verify SearchSelectors.NO_RESULTS includes modern LinkedIn empty state strings."""
    selector = SearchSelectors.NO_RESULTS
    assert "No matching jobs found" in selector
    assert "No matching jobs" in selector
    assert "No jobs found" in selector
    assert "things aren't loading" in selector


@pytest.mark.asyncio
async def test_has_no_results_detection(mock_engine):
    """Test that has_no_results returns True when empty/error state is detected."""
    interactions = AsyncMock()
    interactions.element_exists.return_value = False
    
    page_object = LinkedInSearchPage(mock_engine, interactions)
    
    # Mock page evaluation returning True (indicating empty results)
    mock_engine.page.evaluate.return_value = True
    assert await page_object.has_no_results() is True
    
    # Mock page evaluation returning False
    mock_engine.page.evaluate.return_value = False
    assert await page_object.has_no_results() is False


@pytest.mark.asyncio
async def test_get_total_result_count_parsing(mock_engine):
    """Test get_total_result_count correctly parses integer counts from JS evaluation."""
    page_object = LinkedInSearchPage(AsyncMock(), AsyncMock())
    page_object._engine = mock_engine
    
    # Simulate JS finding 12 results
    mock_engine.page.evaluate.return_value = 12
    count = await page_object.get_total_result_count()
    assert count == 12
    
    # Calculate pages needed
    max_pages = math.ceil(count / 25)
    assert max_pages == 1
    
    # Simulate JS finding 35 results
    mock_engine.page.evaluate.return_value = 35
    count35 = await page_object.get_total_result_count()
    assert count35 == 35
    assert math.ceil(count35 / 25) == 2


@pytest.mark.asyncio
async def test_go_to_next_page_disabled_check(mock_engine):
    """Test that go_to_next_page returns False when next button is aria-disabled or no results found."""
    page_object = LinkedInSearchPage(mock_engine, AsyncMock())
    page_object.has_no_results = AsyncMock(return_value=True)
    
    # If has_no_results is True, go_to_next_page should immediately return False
    assert await page_object.go_to_next_page() is False
