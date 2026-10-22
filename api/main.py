"""
FastAPI application for the Naukri AI Agent dashboard.
Provides REST endpoints wrapping the existing database and agent.
"""

from __future__ import annotations

import subprocess
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse

from api.deps import state as deps
from api.auth.deps import _resolve_secret
from api.routes import (
    accounts as accounts_router,
    agent as agent_router,
    applications as applications_router,
    screening as screening_router,
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
from src.naukri_agent.config.settings import get_settings
from src.naukri_agent.database.repository import SQLAlchemyRepository
from src.naukri_agent.models.db_schema import setup_database_manager


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):

    deps.settings = get_settings()
    deps.db_manager = await setup_database_manager(deps.settings.db_path)
    deps.repo = SQLAlchemyRepository(deps.db_manager)
    await deps.repo.initialize()

    # Defer account resolution to first request to speed up startup
    deps.active_account_email = None
    from api import identity
    from api.tenants import runtime_for
    await asyncio.to_thread(identity.seed_operator)
    app.state.auth_attempts = {}
    for user in await asyncio.to_thread(identity.all_users):
        if not user['is_operator']:
            await runtime_for(user)

    from datetime import UTC, datetime
    from api.webhook_publisher import run_publisher
    from api.scheduler import run_scheduler
    from api.agent_runtime import supervise

    tasks = [asyncio.create_task(run_scheduler()), asyncio.create_task(supervise(deps.repo)),
             asyncio.create_task(run_publisher(datetime.now(UTC)))]
    try:
        yield
    finally:
        from api.remote_verification import controller
        await controller.close()
        from api.tenants import shutdown_tenants
        await shutdown_tenants()
        sync_task = getattr(deps, "application_sync_task", None)
        if sync_task is not None:
            tasks.append(sync_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.to_thread(_cleanup_agent)
        await asyncio.to_thread(multi_agent_router.cleanup_multi_agents)
        await deps.db_manager.engine.dispose()


def _cleanup_agent() -> None:
    proc = deps.agent_process
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


async def get_active_account_email() -> str | None:
    """Lazily resolve and cache the active account email."""
    if deps.active_account_email is not None:
        return deps.active_account_email

    from sqlalchemy import select
    from src.naukri_agent.models.db_schema import NaukriAccount

    try:
        session_factory = await deps.db_manager.get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(NaukriAccount).where(NaukriAccount.is_active).limit(1)
            )
            active = result.scalar_one_or_none()
            if not active and deps.settings and deps.settings.naukri and deps.settings.naukri.email:
                active = NaukriAccount(
                    email=deps.settings.naukri.email.strip(),
                    password=deps.settings.naukri.password,
                    name=deps.settings.naukri.name or deps.settings.naukri.email.split("@")[0],
                    is_active=True,
                    is_primary=True,
                )
                session.add(active)
                await session.commit()
                await session.refresh(active)
            if active:
                deps.active_account_email = active.email
                return active.email
    except Exception:
        pass
    return None


app = FastAPI(
    title="Naukri AI Agent Dashboard",
    version="2.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# API Key Authentication Middleware (added first - innermost)
# ---------------------------------------------------------------------------
# API Key Authentication Middleware
# ---------------------------------------------------------------------------
PUBLIC_PATHS = {"/", "/api/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
PUBLIC_PREFIXES = {"/docs/", "/redoc/", "/api/auth/"}


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "Naukri AI Agent API",
        "docs": "/docs",
        "version": "2.0.0",
    }



@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    from api.deps import current_state, root_state
    from api import identity
    from api.tenants import runtime_for
    from api.auth.jwt import verify_access_token
    import secrets
    import time

    api_key = root_state.settings.dashboard_api_key if root_state.settings else None
    public = request.url.path in PUBLIC_PATHS or any(request.url.path.startswith(prefix) for prefix in PUBLIC_PREFIXES)
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    if not token and request.url.path in ("/api/agent/output/stream", "/api/multi/output/stream"):
        token = request.query_params.get("token", "")
    runtime = root_state
    authorized = bool(api_key and token and secrets.compare_digest(token, api_key))
    if token and not authorized:
        payload = verify_access_token(token, _resolve_secret())
        user = await asyncio.to_thread(identity.find_user, payload.get("sub", "")) if payload else None
        if user:
            runtime = await runtime_for(user)
            authorized = True
    if request.method == "POST" and request.url.path in ("/api/auth/login", "/api/auth/register"):
        attempts = getattr(app.state, "auth_attempts", {})
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        recent = [stamp for stamp in attempts.get(key, []) if stamp > now - 60]
        if len(recent) >= 60:
            return PlainTextResponse('{"detail":"Too many attempts. Try again shortly."}', status_code=429, media_type="application/json")
        if len(attempts) > 10000:
            attempts.clear()
        attempts[key] = recent + [now]
        app.state.auth_attempts = attempts
    if request.method == "OPTIONS" or public or authorized:
        context_token = current_state.set(runtime)
        try:
            response = await call_next(request)
        finally:
            current_state.reset(context_token)
    else:
        response = PlainTextResponse('{"detail":"Unauthorized"}', status_code=401,
            headers={"Content-Type": "application/json", "WWW-Authenticate": "Bearer"})
    # Dashboard data includes credentials, sessions and rapidly changing run state.
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


# GZipMiddleware first (inner) - compresses responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORSMiddleware last (outermost) - handles CORS headers on all responses
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in __import__("os").environ.get("DASHBOARD_ALLOWED_ORIGINS", "https://naukri-ai-autoapply.vercel.app").split(",") if origin.strip()],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "Range",
        "Cache-Control",
    ],
)


# Include routers
app.include_router(auth_router.router)
app.include_router(health_router.router)
app.include_router(stats_router.router)
app.include_router(jobs_router.router)
app.include_router(applications_router.router)
app.include_router(screening_router.router)
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
from api.routes.ai_advisor import router as ai_advisor_router
app.include_router(ai_advisor_router)
from api.routes.career_studio import router as career_studio_router
app.include_router(career_studio_router)
from api.routes.copilot import router as copilot_router
app.include_router(copilot_router)
from api.remote_verification import router as verification_router
app.include_router(verification_router)


if __name__ == "__main__":
    from libs.common import serve

    serve(
        "api.main:app",
        port=8005,
        reload=True,
        reload_dirs=["api", "src"],
    )

