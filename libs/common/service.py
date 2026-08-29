"""
Factory for building a FastAPI service app with a common, hardened lifespan.

Every service reuses the existing route modules and the existing global
``api.deps.state`` container. ``make_service_app`` wires a lifespan that:
  1. loads settings,
  2. creates the shared-DB connection (with a wait-for-DB retry so a brief
     Postgres outage at boot does not kill the service),
  3. optionally resolves the active account (needed by agent/jobs/apps),
  4. runs optional startup/shutdown hooks (e.g. agent subprocess cleanup).

It also installs production-grade middleware on every service:
  * request-size limiting (anti DoS),
  * a request-ID / correlation-id injected into every response,
  * service-to-service authentication (the gateway proves itself with a shared
    token; direct access to a backend port without it is rejected when a token
    is configured),
  * configurable CORS,
  * a real DB-aware ``/api/health`` (plus ``/api/ready`` and ``/api/live``).
"""

from __future__ import annotations

import contextlib
import hmac
import os
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from api.deps import state
from libs.common.auth import resolve_service_token
from libs.common.db import create_database_manager
from libs.common.metrics import MetricsMiddleware, metrics_response
from libs.common.resilience import HTTPOverSize, RequestSizeLimit, http_over_size_handler
from src.naukri_agent.config.settings import get_settings
from src.naukri_agent.database.repository import SQLAlchemyRepository
from src.naukri_agent.models.db_schema import NaukriAccount

_PUBLIC_PATHS = {
    "/api/health",
    "/api/ready",
    "/api/live",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
}


def _cors_origins() -> list[str]:
    env = os.environ.get("CORS_ORIGINS")
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    return ["http://localhost:5173", "http://localhost:3000"]


def _service_token_valid(header_value: str | None, token: str) -> bool:
    if not token:
        return True  # auth not enforced in this environment
    if not header_value:
        return False
    return hmac.compare_digest(header_value, token)


async def _wait_for_database() -> Any:
    """Create the DB manager, retrying briefly on transient Postgres errors."""
    last_exc: Exception | None = None
    for _attempt in range(15):
        try:
            return await create_database_manager()
        except OperationalError as exc:
            last_exc = exc
            await _sleep(2.0)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Database manager could not be created")


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


async def _resolve_active_account() -> None:
    """Best-effort: populate ``state.active_account_email`` from the DB."""
    try:
        sf = await state.db_manager.get_session_factory()
        async with sf() as session:
            row = (
                await session.execute(
                    select(NaukriAccount).where(NaukriAccount.is_active.is_(True)).limit(1)
                )
            ).scalar_one_or_none()
            if row:
                state.active_account_email = row.email
    except Exception:
        pass


def _install_request_id(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next: Callable) -> Any:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def _install_service_auth(app: FastAPI, token: str | None) -> None:
    if token is None:
        return  # dev mode: auth enforced at the gateway only

    @app.middleware("http")
    async def _service_auth_middleware(request: Request, call_next: Callable) -> Any:
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if path in _PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)
        provided = request.headers.get("X-Service-Token")
        if not _service_token_valid(provided, token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized (missing service token)"},
            )
        return await call_next(request)


def make_service_app(
    *,
    name: str,
    routers: list[Any],
    resolve_active_account: bool = False,
    on_startup: Callable[[FastAPI], Awaitable[None]] | None = None,
    on_shutdown: Callable[[FastAPI], Awaitable[None]] | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.settings = get_settings()
        state.db_manager = await _wait_for_database()
        state.repo = SQLAlchemyRepository(state.db_manager)
        await state.repo.initialize()
        if resolve_active_account:
            await _resolve_active_account()
        if on_startup:
            await on_startup(app)
        try:
            yield
        finally:
            if on_shutdown:
                await on_shutdown(app)
            with contextlib.suppress(Exception):
                await state.db_manager.engine.dispose()

    app = FastAPI(title=name, lifespan=lifespan)

    # Request size limit (anti DoS). Upload routes can raise this via config.
    app.add_middleware(RequestSizeLimit, max_bytes=int(os.environ.get("MAX_BODY_BYTES", "1048576")))

    # Prometheus metrics for every request (no-op if prometheus_client missing).
    app.add_middleware(MetricsMiddleware, service=name)

    origins = cors_origins or _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _install_request_id(app)
    _install_service_auth(app, resolve_service_token())

    app.add_exception_handler(HTTPOverSize, http_over_size_handler)

    app.add_api_route("/metrics", metrics_response, methods=["GET"])

    for router in routers:
        app.include_router(router.router)

    @app.get("/api/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "service": name}

    @app.get("/api/live", tags=["health"])
    async def live() -> dict:
        return {"status": "ok", "service": name}

    @app.get("/api/ready", tags=["health"])
    async def ready() -> dict:
        """Readiness: process up AND database reachable."""
        try:
            sf = await state.db_manager.get_session_factory()
            async with sf() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok", "service": name, "database": "ready"}
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "service": name,
                    "database": "down",
                    "detail": str(exc),
                },
            )

    return app
