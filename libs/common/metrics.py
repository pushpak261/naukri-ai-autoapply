"""
Shared Prometheus metrics for every service and the gateway.

Exposes a small FastAPI middleware that records request counts, latency, and
in-flight requests, plus a ``/metrics`` exposition helper. The gateway and
``make_service_app`` both wire this in so every process exposes the same
telemetry on ``:<port>/metrics`` for a Prometheus scrape job.

If ``prometheus_client`` is unavailable (e.g. trimmed deployment) the middleware
becomes a no-op so the app still boots.
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _HAVE_PROM = True
except Exception:  # pragma: no cover - optional dependency
    _HAVE_PROM = False

from starlette.middleware.base import BaseHTTPMiddleware


if _HAVE_PROM:
    REQUEST_COUNT = Counter(
        "http_requests_total",
        "Total HTTP requests handled.",
        ["method", "endpoint", "status_code", "service"],
    )
    REQUEST_LATENCY = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds.",
        ["method", "endpoint", "service"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    )
    INFLIGHT = Gauge(
        "http_requests_in_flight",
        "Number of requests currently in flight.",
        ["service"],
    )
    SERVER_ERRORS = Counter(
        "http_server_errors_total",
        "Count of 5xx responses returned by this process.",
        ["service"],
    )
    CIRCUIT_BREAKER_OPEN = Gauge(
        "gateway_circuit_breaker_open",
        "1 if an upstream circuit breaker is currently open (fail-fast).",
        ["upstream"],
    )
    AGENT_LAST_RUN_TIMESTAMP = Gauge(
        "agent_last_run_timestamp_seconds",
        "Epoch seconds of the last agent run start/finish (dead-man's-switch).",
    )
    AGENT_LAST_APPLY_TIMESTAMP = Gauge(
        "agent_last_apply_timestamp_seconds",
        "Epoch seconds of the last successful job application (dead-man's-switch).",
    )
    AGENT_RUNNING = Gauge(
        "agent_running",
        "1 while an agent run is in progress.",
    )
    AGENT_BLOCKED = Gauge(
        "agent_blocked",
        "1 when the agent has paused due to an external block (captcha/OTP/IP-ban).",
    )
else:  # pragma: no cover
    REQUEST_COUNT = REQUEST_LATENCY = INFLIGHT = SERVER_ERRORS = None
    CIRCUIT_BREAKER_OPEN = AGENT_LAST_RUN_TIMESTAMP = AGENT_LAST_APPLY_TIMESTAMP = AGENT_RUNNING = (
        AGENT_BLOCKED
    ) = None


def _endpoint_label(path: str) -> str:
    if len(path) > 96:
        return path[:96] + "..."
    return path


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record Prometheus metrics for every request (no-op if unavailable)."""

    def __init__(self, app: Any, service: str) -> None:
        super().__init__(app)
        self.service = service

    async def dispatch(self, request: Any, call_next: Any) -> Any:
        if not _HAVE_PROM:
            return await call_next(request)
        path = request.url.path
        if path == "/metrics":
            return await call_next(request)
        INFLIGHT.labels(self.service).inc()
        try:
            with REQUEST_LATENCY.labels(request.method, _endpoint_label(path), self.service).time():
                response = await call_next(request)
            REQUEST_COUNT.labels(
                request.method,
                _endpoint_label(path),
                response.status_code,
                self.service,
            ).inc()
            return response
        finally:
            INFLIGHT.labels(self.service).dec()


def metrics_response() -> Any:
    """FastAPI/Starlette response exposing the Prometheus text format."""
    from starlette.responses import Response

    if not _HAVE_PROM:
        return Response("metrics disabled\n", media_type="text/plain")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
