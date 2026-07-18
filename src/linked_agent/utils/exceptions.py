"""
Custom exceptions for the LinkedIn Agent.
"""

from __future__ import annotations


class LinkedInAgentError(Exception):
    """Base exception for all LinkedIn agent errors."""

    pass


class BrowserAutomationError(LinkedInAgentError):
    """Raised when browser automation fails."""

    pass


class LoginError(LinkedInAgentError):
    """Raised when LinkedIn login fails."""

    pass


class LLMAPIError(LinkedInAgentError):
    """Raised when LLM API calls fail."""

    pass


class LLMQuotaExceededError(LLMAPIError):
    """Raised when LLM API quota is exceeded."""

    def __init__(self, message: str = "", is_daily_quota: bool = False) -> None:
        super().__init__(message)
        self.is_daily_quota = is_daily_quota


class ConfigurationError(LinkedInAgentError):
    """Raised when configuration is invalid or missing."""

    pass


class RateLimitError(LinkedInAgentError):
    """Raised when LinkedIn rate limits are hit."""

    pass
