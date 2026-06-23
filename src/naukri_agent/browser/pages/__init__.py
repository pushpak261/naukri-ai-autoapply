"""
Page Object package for encapsulating low-level browser DOM interactions.
"""

from src.naukri_agent.browser.pages.base import BasePage
from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.browser.pages.login import LoginPage
from src.naukri_agent.browser.pages.search import SearchPage

__all__ = ["BasePage", "LoginPage", "SearchPage", "JobDetailPage"]
