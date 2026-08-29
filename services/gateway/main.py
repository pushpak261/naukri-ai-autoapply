"""
API Gateway (BFF) for the Naukri microservice platform.

Single external entry point. Responsibilities:
  * Verify the user's JWT locally (HS256, shared secret) on protected routes.
  * Reverse-proxy ``/api/<service>/*`` to the correct backend over HTTP, with
    a shared pooled client, per-route timeouts, retries (GET), per-upstream
    circuit breakers, and rate limiting. Only healthy/closed breakers are used
    (open breaker => immediate 503, no 120s hang).
  * Stream Server-Sent-Events (agent output) transparently (long timeouts).
  * Propagate correlation id (``X-Request-ID``) and service token downstream.
  * Enforce request-size limits and rate limits at the edge.
  * Graceful shutdown (drain in-flight streams, close the client).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from libs.common import SERVICE_PORTS
from libs.common.auth import resolve_jwt_secret, resolve_service_token, verify_access_token
from libs.common.metrics import (
    CIRCUIT_BREAKER_OPEN,
    SERVER_ERRORS,
    MetricsMiddleware,
    metrics_response,
)
from libs.common.resilience import (
    CircuitBreaker,
    CircuitOpen,
    DEFAULT_MAX_BODY_BYTES,
    HTTPOverSize,
    RateLimiter,
    RequestSizeLimit,
    http_over_size_handler,
)

# (path_prefix, service_name) — most specific first.
ROUTES: list[tuple[str, str]] = [
    ("/api/auth", "auth"),
    ("/api/accounts", "auth"),
    ("/api/config", "config"),
    ("/api/jobs", "jobs"),
    ("/api/market-intel", "jobs"),
    ("/api/resume", "resume"),
    ("/api/resume-profile", "resume"),
    ("/api/resume-optimization", "resume"),
    ("/api/applications", "applications"),
    ("/api/run-logs", "applications"),
    ("/api/stats", "applications"),
    ("/api/analytics", "applications"),
    ("/api/application-statuses", "applications"),
    ("/api/scam-detector", "ai"),
    ("/api/cache/match-cache", "ai"),
    ("/api/ai", "ai"),
    ("/api/agent", "agent"),
    ("/api/multi", "agent"),
    ("/api/autopilot", "agent"),
    ("/api/webhooks", "agent"),
    ("/api/session", "agent"),
    ("/api/sessions", "agent"),
    ("/api/backups", "data"),
    ("/api/export", "data"),
    ("/api/import", "data"),
    ("/api/logs", "data"),
    ("/api/metrics", "data"),
    ("/api/data", "data"),
]

PUBLIC_PATHS = {"/api/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
PUBLIC_PREFIXES = ("/api/auth/",)

# Routes that stream for a long time (agent output, autopilot, sessions).
STREAM_PREFIXES = ("/api/agent", "/api/multi", "/api/autopilot", "/api/session", "/api/sessions")


def service_url(name: str) -> str:
    return os.environ.get(f"{name.upper()}_SERVICE_URL") or f"http://localhost:{SERVICE_PORTS[name]}"


def _resolve_service(path: str) -> str | None:
    for prefix, svc in sorted(ROUTES, key=lambda r: len(r[0]), reverse=True):
        if path.startswith(prefix):
            return svc
    return None


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def _is_stream(path: str) -> bool:
    return any(path.startswith(p) for p in STREAM_PREFIXES)


def _cors_origins() -> list[str]:
    env = os.environ.get("CORS_ORIGINS")
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    return ["http://localhost:5173", "http://localhost:3000"]


# ---------------------------------------------------------------------------
# App + lifespan
# ---------------------------------------------------------------------------

app = FastAPI(title="naukri-gateway", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestSizeLimit, max_bytes=int(os.environ.get("MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))))
app.add_middleware(MetricsMiddleware, service="gateway")
app.add_exception_handler(HTTPOverSize, http_over_size_handler)
app.add_api_route("/metrics", metrics_response, methods=["GET"])

_state: dict[str, Any] = {}
_rate_limiter = RateLimiter(rate=float(os.environ.get("GATEWAY_RATE", "20")), capacity=float(os.environ.get("GATEWAY_BURST", "40")))


@app.on_event("startup")
async def _startup() -> None:
    # Fail fast in production if we cannot verify user tokens.
    if os.environ.get("PROD") == "true" and not resolve_jwt_secret():
        raise RuntimeError("PROD=true but JWT_SECRET is not configured; gateway cannot verify tokens.")
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=40)
    _state["client"] = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=2.0),
        limits=limits,
    )


@app.on_event("shutdown")
async def _shutdown() -> None:
    client = _state.get("client")
    if client is not None:
        await client.aclose()


def _client() -> httpx.AsyncClient:
    return _state["client"]


def _service_token() -> str | None:
    return resolve_service_token()


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Gateway health plus a best-effort liveness probe of each service."""
    services: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=0.5) as probe:
        for name in SERVICE_PORTS:
            if name == "gateway":
                continue
            try:
                r = await probe.get(service_url(name) + "/api/health")
                services[name] = "up" if r.status_code == 200 else "down"
            except Exception:
                services[name] = "down"
    return {"status": "ok", "gateway": "up", "services": services}


@app.get("/api")
async def api_index() -> dict[str, Any]:
    return {
        "gateway": "naukri microservice platform",
        "services": {name: service_url(name) for name in SERVICE_PORTS if name != "gateway"},
    }


# ---------------------------------------------------------------------------
# Auth (JWT verification at the edge)
# ---------------------------------------------------------------------------


def _require_user(request: Request) -> str | None:
    """Verify the bearer JWT locally; return the user email or ``None``."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer ") :].strip()
    payload = verify_access_token(token)
    if payload is None:
        return None
    return payload.get("sub")


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------


async def _proxy(request: Request) -> Any:
    path = request.url.path

    user: str | None = None
    if not _is_public(path):
        user = _require_user(request)
        if user is None:
            return JSONResponse(
                '{"detail":"Unauthorized"}',
                status_code=401,
                headers={"Content-Type": "application/json", "WWW-Authenticate": "Bearer"},
            )

    service = _resolve_service(path)
    if not service:
        raise HTTPException(status_code=404, detail=f"No service mapped for path: {path}")

    breaker = CircuitBreaker.for_upstream(service)
    if not breaker.allow():
        if CIRCUIT_BREAKER_OPEN is not None:
            CIRCUIT_BREAKER_OPEN.labels(service).set(1)
        if SERVER_ERRORS is not None:
            SERVER_ERRORS.labels("gateway").inc()
        return JSONResponse(
            status_code=503,
            content={"detail": f"Service '{service}' unavailable (circuit open)", "retry_after": 30},
            headers={"Retry-After": "30"},
        )

    url = service_url(service).rstrip("/") + path
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    if user:
        headers["X-User-Id"] = user
    token = _service_token()
    if token:
        headers["X-Service-Token"] = token
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    headers["X-Request-ID"] = request_id

    body = await request.body()
    stream = _is_stream(path)
    timeout = httpx.Timeout(3600.0, connect=5.0) if stream else httpx.Timeout(30.0, connect=5.0)

    is_get = request.method == "GET"
    last_exc: Exception | None = None
    for attempt in range(3 if is_get else 1):
        try:
            upstream = _client().build_request(
                request.method,
                url,
                params=request.url.query,
                headers=headers,
                content=body,
                timeout=timeout,
            )
            response = await _client().send(upstream, stream=True)
            breaker.record_success()
            if CIRCUIT_BREAKER_OPEN is not None:
                CIRCUIT_BREAKER_OPEN.labels(service).set(0)
            if response.status_code >= 500 and SERVER_ERRORS is not None:
                SERVER_ERRORS.labels("gateway").inc()
            return _stream_response(response, request_id)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            breaker.record_failure()
            if not is_get:
                break
            await _sleep(0.2 * (attempt + 1))
        except CircuitOpen:
            if CIRCUIT_BREAKER_OPEN is not None:
                CIRCUIT_BREAKER_OPEN.labels(service).set(1)
            if SERVER_ERRORS is not None:
                SERVER_ERRORS.labels("gateway").inc()
            return JSONResponse(
                status_code=503,
                content={"detail": f"Service '{service}' unavailable (circuit open)", "retry_after": 30},
                headers={"Retry-After": "30"},
            )
        except httpx.HTTPStatusError as exc:
            # 5xx from backend on GET: retry once.
            last_exc = exc
            if not is_get or exc.response.status_code < 500:
                break
            breaker.record_failure()
            await _sleep(0.2 * (attempt + 1))

    if CIRCUIT_BREAKER_OPEN is not None:
        CIRCUIT_BREAKER_OPEN.labels(service).set(1)
    if SERVER_ERRORS is not None:
        SERVER_ERRORS.labels("gateway").inc()
    return JSONResponse(
        status_code=502,
        content={"detail": f"Bad gateway calling '{service}': {type(last_exc).__name__ if last_exc else 'unknown'}"},
    )


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _stream_response(response: httpx.Response, request_id: str) -> StreamingResponse:
    excluded = {"content-length", "transfer-encoding", "connection", "keep-alive"}
    resp_headers = {k: v for k, v in response.headers.items() if k.lower() not in excluded}
    resp_headers["X-Request-ID"] = request_id

    async def _stream():
        try:
            async for chunk in response.aiter_raw():
                yield chunk
        finally:
            await response.aclose()

    return StreamingResponse(
        _stream(),
        status_code=response.status_code,
        headers=resp_headers,
        media_type=response.headers.get("content-type"),
    )


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy(request: Request):
    # Rate limit by client IP (skip public OPTIONS preflight).
    if request.method != "OPTIONS":
        client_ip = request.client.host if request.client else "unknown"
        if not await _rate_limiter.consume(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limited. Slow down and retry shortly."},
                headers={"Retry-After": "5"},
            )
    return await _proxy(request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("GATEWAY_PORT", "8000")))
