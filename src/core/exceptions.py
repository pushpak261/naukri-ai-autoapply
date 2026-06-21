"""
Custom exception classes for the Naukri Agent.
Enforces robust error handling and categorizes failures.
"""


class AgentException(Exception):
    """Base exception class for all agent-related errors."""

    pass


class LLMAPIError(AgentException):
    """Raised when communication with the LLM API fails."""

    pass


class LLMQuotaExceededError(LLMAPIError):
    """
    Raised specifically when the LLM provider reports a quota/rate-limit
    exhaustion (HTTP 429 / RESOURCE_EXHAUSTED).

    Kept distinct from the generic LLMAPIError because callers need to react
    differently: a transient network hiccup is worth retrying, but a daily
    request-quota exhaustion is not — retrying just wastes time and (if the
    provider counts failed-but-quota-blocked attempts) potentially more quota.
    """

    def __init__(self, message: str, is_daily_quota: bool = False) -> None:
        super().__init__(message)
        self.is_daily_quota = is_daily_quota


class BrowserAutomationError(AgentException):
    """Raised when browser interactions (e.g., Playwright) fail."""

    pass


class DatabaseOperationError(AgentException):
    """Raised when a database query or operation fails."""

    pass
