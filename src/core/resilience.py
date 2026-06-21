"""
Resilience patterns for the Naukri Agent.

Implements retries with exponential backoff for network/API calls,
and a Circuit Breaker to gracefully halt execution on consecutive failures.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Standard retry decorator for network/API calls
# Retries 3 times, waiting 2s, 4s, 8s
network_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class CircuitBreaker:
    """
    Halts execution if a failure threshold is reached.
    """

    def __init__(self, failure_threshold: int = 5):
        self.failure_threshold = failure_threshold
        self.failures = 0
        self.is_open = False

    def record_success(self) -> None:
        """Reset failures on success."""
        self.failures = 0
        self.is_open = False

    def record_failure(self) -> None:
        """Increment failure count and open circuit if threshold reached."""
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.is_open = True
            logger.error(f"Circuit Breaker OPEN! {self.failures} consecutive failures.")

    def check(self) -> None:
        """Raise exception if circuit is open."""
        if self.is_open:
            raise RuntimeError("Circuit Breaker is OPEN due to consecutive failures. Halting.")
