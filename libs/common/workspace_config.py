"""Shared account settings used by the LinkedIn API and agent process."""

from pathlib import Path

import yaml

SHARED_SECTIONS = ("ai", "application", "resume", "profile", "exclusions")


def load_linkedin_workspace_config(root: Path) -> dict:
    shared_path = root / "config.yaml"
    shared = yaml.safe_load(shared_path.read_text()) if shared_path.exists() else {}
    shared = shared or {}
    # Search formats are platform-specific: Naukri freshness is an integer,
    # whereas LinkedIn uses past_week/past_month/etc.
    config = {
        key: dict(shared[key]) for key in SHARED_SECTIONS if isinstance(shared.get(key), dict)
    }
    # These search preferences have identical meanings on both platforms.
    # Platform-specific values below may still override them explicitly.
    shared_search = shared.get("search", {})
    if isinstance(shared_search, dict):
        config["search"] = {
            key: shared_search[key]
            for key in ("keywords", "locations", "max_pages", "sort_by", "enable_heuristics")
            if key in shared_search
        }
    platform_path = root / "linkedin_config.yaml"
    platform = yaml.safe_load(platform_path.read_text()) if platform_path.exists() else {}
    for key, value in (platform or {}).items():
        config[key] = {**config.get(key, {}), **value} if isinstance(value, dict) else value
    return config
