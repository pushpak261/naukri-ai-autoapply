"""
Persist user-editable configuration overrides in SQLite.

Dashboard and API changes are stored here so config.yaml remains a stable
defaults/bootstrap file and is not rewritten on every toggle.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "naukri_agent.db"


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _dot_key(parts: list[str]) -> str:
    return ".".join(parts)


def _set_nested(d: dict, keys: list[str], value: Any) -> None:
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def unflatten_overrides(flat: dict[str, Any]) -> dict:
    nested: dict = {}
    for key, value in flat.items():
        _set_nested(nested, key.split("."), value)
    return nested


def deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_overrides(db_path: Path | None = None) -> dict:
    """Load all stored config overrides as a nested dict."""
    path = db_path or DEFAULT_DB_PATH
    if not path.exists():
        return {}
    try:
        conn = sqlite3.connect(path)
        _ensure_table(conn)
        rows = conn.execute("SELECT key, value FROM app_config").fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    flat = {key: json.loads(value) for key, value in rows}
    return unflatten_overrides(flat)


def save_override(key: str, value: Any, db_path: Path | None = None) -> None:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT INTO app_config (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, json.dumps(value), datetime.now(UTC).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def apply_updates(
    updates: list[tuple[list[str], Any]],
    db_path: Path | None = None,
) -> None:
    """Persist a batch of nested config updates to the database."""
    for keys, value in updates:
        if value is not None:
            save_override(_dot_key(keys), value, db_path)
