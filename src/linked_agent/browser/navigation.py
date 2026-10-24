"""Retry brief transport outages without rejecting a suitable job as a mismatch."""

import asyncio

from playwright.async_api import Error as PlaywrightError

from src.linked_agent.utils.exceptions import BrowserAutomationError
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)
NETWORK_ERRORS = (
    "ERR_NAME_NOT_RESOLVED",
    "ERR_NETWORK_CHANGED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_TIMED_OUT",
    "ERR_CONNECTION_REFUSED",
)


class NetworkUnavailableError(BrowserAutomationError):
    """Connectivity stayed unavailable after bounded retries of the same listing."""


async def navigate(page, url, timeout=30000):
    for attempt in range(4):
        try:
            return await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except PlaywrightError as error:
            if not any(code in str(error) for code in NETWORK_ERRORS):
                raise
            if attempt == 3:
                raise NetworkUnavailableError(
                    "LinkedIn connectivity is unavailable after four attempts. "
                    "Reconnect and restart; remaining jobs have not been rejected or submitted."
                ) from error
            delay = 5 * (2**attempt)
            logger.warning(
                "LinkedIn network interrupted; retrying the same listing in %s seconds (%s/4).",
                delay,
                attempt + 1,
            )
            await asyncio.sleep(delay)
