# src/config/__init__.py
"""Configuration management for the Naukri Agent."""

from src.naukri_agent.config.settings import Settings, get_settings

__all__ = ["get_settings", "Settings"]
