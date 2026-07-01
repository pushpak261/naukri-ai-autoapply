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
