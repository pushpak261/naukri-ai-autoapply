"""Backward-compatible re-exports after package layout refactor."""

from src.naukri_agent.utils.exceptions import (
    AgentException,
    BrowserAutomationError,
    LLMAPIError,
    LLMQuotaExceededError,
)

__all__ = [
    "AgentException",
    "BrowserAutomationError",
    "LLMAPIError",
    "LLMQuotaExceededError",
]
