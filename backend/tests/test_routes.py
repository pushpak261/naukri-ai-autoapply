"""Tests for FastAPI routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_current_run_idle(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/runs/current")
    assert res.status_code == 200
    assert res.json()["status"] == "idle"


@pytest.mark.asyncio
async def test_list_runs_keywords_are_lists(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/runs?limit=20")
    assert res.status_code == 200
    for run in res.json():
        assert isinstance(run["keywords"], list)


@pytest.mark.asyncio
async def test_config_summary_no_secrets(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/config/summary")
    assert res.status_code == 200
    data = res.json()
    assert "keywords" in data
    assert "password" not in data
    assert "gemini_api_key" not in data


@pytest.mark.asyncio
async def test_update_search_experience(app, tmp_path, monkeypatch):
    from src.naukri_agent.config import settings as settings_module

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "search:\n  experience_min: 0\n  experience_max: 1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "PROJECT_ROOT", tmp_path)
    settings_module.get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/config/search/experience",
            json={"experience_min": 2, "experience_max": 5},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["experience_min"] == 2
    assert data["experience_max"] == 5
    assert "experience_min: 2" in config_path.read_text(encoding="utf-8")
    settings_module.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_update_search_experience_rejects_invalid_range(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.put(
            "/api/v1/config/search/experience",
            json={"experience_min": 5, "experience_max": 2},
        )
    assert res.status_code == 422
