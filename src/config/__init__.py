# src/config/__init__.py
"""Configuration management for the Naukri Agent."""

from src.config.settings import get_settings, Settings

__all__ = ["get_settings", "Settings"]
