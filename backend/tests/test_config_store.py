"""Tests for database-backed configuration overrides."""

from __future__ import annotations

import json
import sqlite3

import pytest

from src.naukri_agent.config import settings as settings_module
from src.naukri_agent.config.store import (
    apply_updates,
    deep_merge,
    load_overrides,
    unflatten_overrides,
)


def test_deep_merge_nested_dicts():
    base = {"application": {"daily_cap": 25, "dry_run": False}}
    override = {"application": {"answer_questions_with_pdf": False}}
    merged = deep_merge(base, override)
    assert merged == {
        "application": {
            "daily_cap": 25,
            "dry_run": False,
            "answer_questions_with_pdf": False,
        }
    }


def test_unflatten_overrides():
    flat = {
        "application.answer_questions_with_pdf": False,
        "search.experience_min": 2,
    }
    assert unflatten_overrides(flat) == {
        "application": {"answer_questions_with_pdf": False},
        "search": {"experience_min": 2},
    }


def test_apply_and_load_overrides(tmp_path, monkeypatch):
    db_path = tmp_path / "naukri_agent.db"
    monkeypatch.setattr("src.naukri_agent.config.store.DEFAULT_DB_PATH", db_path)

    apply_updates([(["application", "answer_questions_with_pdf"], False)], db_path)

    overrides = load_overrides(db_path)
    assert overrides["application"]["answer_questions_with_pdf"] is False

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT value FROM app_config WHERE key = ?",
        ("application.answer_questions_with_pdf",),
    ).fetchone()
    conn.close()
    assert json.loads(row[0]) is False


def test_get_settings_merges_db_over_yaml(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "naukri_agent.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "application:\n  answer_questions_with_pdf: true\n  daily_cap: 25\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(settings_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("src.naukri_agent.config.store.DEFAULT_DB_PATH", db_path)
    settings_module.get_settings.cache_clear()

    apply_updates([(["application", "answer_questions_with_pdf"], False)], db_path)
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()
    assert settings.application.answer_questions_with_pdf is False
    assert settings.application.daily_cap == 25
    assert "answer_questions_with_pdf: false" not in config_path.read_text(encoding="utf-8")

    settings_module.get_settings.cache_clear()
