# src/browser/__init__.py
"""Browser automation layer for the Naukri Agent."""

from src.naukri_agent.browser.apply import JobApplier
from src.naukri_agent.browser.engine import PlaywrightEngine
from src.naukri_agent.browser.interactions import HumanInteractions
from src.naukri_agent.browser.login import LoginHandler
from src.naukri_agent.browser.search import JobSearcher

__all__ = ["PlaywrightEngine", "HumanInteractions", "LoginHandler", "JobSearcher", "JobApplier"]
