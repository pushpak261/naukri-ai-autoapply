"""
Page Object package for LinkedIn browser automation.
"""

from src.linked_agent.browser.pages.base import BasePage
from src.linked_agent.browser.pages.login import LinkedInLoginPage
from src.linked_agent.browser.pages.search import LinkedInSearchPage
from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage

__all__ = ["BasePage", "LinkedInLoginPage", "LinkedInSearchPage", "LinkedInJobDetailPage"]
