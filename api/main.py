"""
FastAPI application for the Naukri AI Agent dashboard.
Provides REST endpoints wrapping the existing database and agent.
"""

from __future__ import annotations

import re
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from api.deps import state as deps
from api.routes import (
    accounts as accounts_router,
    agent as agent_router,
    applications as applications_router,
    auth as auth_router,
    config as config_router,
    data as data_router,
    health as health_router,
    jobs as jobs_router,
    resume as resume_router,
    resume_optimization as resume_optimization_router,
    scam_detector as scam_detector_router,
    stats as stats_router,
    autopilot as autopilot_router,
    market_intel as market_intel_router,
    webhooks as webhooks_router,
    multi_agent as multi_agent_router,
)
from src.naukri_agent.config.settings import Settings, get_settings
from src.naukri_agent.database.manager import DatabaseManager
from src.naukri_agent.database.repository import SQLAlchemyRepository
from src.naukri_agent.models.db_schema import setup_database_manager


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import select
    from src.naukri_agent.models.db_schema import NaukriAccount

    deps.settings = get_settings()
    deps.db_manager = await setup_database_manager(deps.settings.db_path)
    deps.repo = SQLAlchemyRepository(deps.db_manager)
    await deps.repo.initialize()

    # Resolve and set the active account email on startup
    try:
        session_factory = await deps.db_manager.get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(NaukriAccount).where(NaukriAccount.is_active == True).limit(1)
            )
            active = result.scalar_one_or_none()
            if active:
                deps.active_account_email = active.email
    except Exception:
        pass

    yield
    _cleanup_agent()
    multi_agent_router.cleanup_multi_agents()


def _cleanup_agent() -> None:
    proc = deps.agent_process
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


app = FastAPI(
    title="Naukri AI Agent Dashboard",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API Key Authentication Middleware
# ---------------------------------------------------------------------------
PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
PUBLIC_PREFIXES = {"/docs/", "/redoc/", "/api/auth/"}


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    api_key = deps.settings.dashboard_api_key if deps.settings else None
    if not api_key:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    if request.url.path in PUBLIC_PATHS or any(
        request.url.path.startswith(p) for p in PUBLIC_PREFIXES
    ):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and auth_header.removeprefix("Bearer ").strip() == api_key:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    return PlainTextResponse(
        '{"detail":"Unauthorized"}',
        status_code=401,
        headers={"Content-Type": "application/json", "WWW-Authenticate": "Bearer"},
    )


# Include routers
app.include_router(auth_router.router)
app.include_router(health_router.router)
app.include_router(stats_router.router)
app.include_router(jobs_router.router)
app.include_router(applications_router.router)
app.include_router(agent_router.router)
app.include_router(config_router.router)
app.include_router(data_router.router)
app.include_router(resume_router.router)
app.include_router(resume_optimization_router.router)
app.include_router(scam_detector_router.router)
app.include_router(autopilot_router.router)
app.include_router(market_intel_router.router)
app.include_router(accounts_router.router)
app.include_router(webhooks_router.router)
app.include_router(multi_agent_router.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8005,
        reload=True,
        reload_dirs=["api", "src"],
    )
