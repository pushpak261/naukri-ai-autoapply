"""
Base Page Object for LinkedIn browser automation.
Provides access to browser engine and human interactions.
"""

from __future__ import annotations

from typing import Any

from src.linked_agent.bot.interfaces import IBrowserEngine, IBrowserInteractions


class BasePage:
    """
    Base class for all LinkedIn page objects.
    Encapsulates Playwright engine and interaction primitives.
    """

    def __init__(self, engine: IBrowserEngine, interactions: IBrowserInteractions) -> None:
        self._engine = engine
        self._interactions = interactions

    @property
    def page(self) -> Any:
        """Public access to the underlying Playwright page."""
        return self._engine.page

    async def close_popups(self) -> None:
        """Close any blocking popups/modals."""
        await self._interactions.close_popups()

    async def action_delay(self) -> None:
        """Execute action delay from interactions."""
        await self._interactions.action_delay()
