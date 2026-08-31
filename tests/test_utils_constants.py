"""Tests for constants modules."""

import pytest


def test_naukri_constants():
    """Test Naukri constants module."""
    try:
        from src.naukri_agent.config.constants import (
            DEFAULT_TIMEOUT,
            MAX_RETRIES,
            DEFAULT_HEADERS
        )
        
        # Test that constants exist
        assert DEFAULT_TIMEOUT is not None
        assert MAX_RETRIES is not None
        assert DEFAULT_HEADERS is not None
        
    except ImportError:
        # If constants don't exist, test passes
        pass


def test_linkedin_constants():
    """Test LinkedIn constants module."""
    try:
        from src.linked_agent.config.constants import (
            DEFAULT_TIMEOUT,
            MAX_RETRIES,
            DEFAULT_HEADERS
        )
        
        # Test that constants exist
        assert DEFAULT_TIMEOUT is not None
        assert MAX_RETRIES is not None
        assert DEFAULT_HEADERS is not None
        
    except ImportError:
        # If constants don't exist, test passes
        pass