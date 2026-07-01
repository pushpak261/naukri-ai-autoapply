"""
Base Page Object for Naukri browser automation.
Provides access to browser engine and human interactions.
"""

from __future__ import annotations

from src.naukri_agent.core.interfaces import IBrowserEngine, IBrowserInteractions


class BasePage:
    """
    Base class for all Naukri page objects.
    Encapsulates Playwright engine and interaction primitives.
    """

    def __init__(self, engine: IBrowserEngine, interactions: IBrowserInteractions) -> None:
        self._engine = engine
        self._interactions = interactions

    async def close_popups(self) -> None:
        """Close any blocking popups/chatbots."""
        await self._interactions.close_popups()

    async def action_delay(self) -> None:
        """Execute action delay from interactions."""
        await self._interactions.action_delay()
