"""
Shared resilience primitives for the Naukri microservice platform.

These helpers implement the core fault-tolerance patterns needed for a system
that must survive real-time, failure-prone scenarios:

  * ``async_retry``      — retries with exponential backoff + jitter.
  * ``CircuitBreaker``   — per-upstream circuit breaker (open/half-open/closed).
  * ``RateLimiter``      — in-memory token-bucket rate limiter (per key).
  * ``RequestSizeLimit`` — ASGI middleware rejecting oversized bodies.

They are dependency-light (``tenacity`` for retry) and safe to use from both
the gateway and individual services.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------

_RETRYABLE_HTTPX = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.RemoteProtocolError,
    httpx.TransportError,
)


def is_retryable_httpx_error(exc: BaseException) -> bool:
    """Return True for httpx errors that are safe to retry (idempotent caller)."""
    return isinstance(exc, _RETRYABLE_HTTPX)


def async_retry(
    *,
    max_attempts: int = 3,
    initial: float = 0.2,
    max_wait: float = 5.0,
    retry_on: Callable[[BaseException], bool] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    Decorator that retries an async coroutine with exponential backoff + jitter.

    By default retries on transient httpx transport/timeout errors. Pass
    ``retry_on`` to customise which exceptions are retryable (e.g. specific
    DB operational errors).
    """

    def _predicate(exc: BaseException) -> bool:
        if retry_on is not None:
            return bool(retry_on(exc))
        return is_retryable_httpx_error(exc)

    return retry(
        retry=retry_if_exception(_predicate),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=initial, max=max_wait),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """
    A minimal async-safe circuit breaker.

    States:
      * CLOSED   — requests flow normally; failures are counted.
      * OPEN     — requests fail fast until the cooldown elapses.
      * HALF_OPEN — a single trial request is allowed; success closes, failure reopens.

    Instances are looked up by ``name`` via :meth:`for_upstream` so the whole
    process shares one breaker per dependency.
    """

    _breakers: dict[str, CircuitBreaker] = {}

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        half_open_max: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._half_open_max = half_open_max
        self._failures = 0
        self._state = "closed"
        self._opened_at = 0.0
        self._half_open_allowed = 0

    @classmethod
    def for_upstream(cls, name: str, **kwargs: Any) -> CircuitBreaker:
        """Return (creating if needed) the shared breaker for an upstream."""
        br = cls._breakers.get(name)
        if br is None:
            br = cls(**kwargs)
            cls._breakers[name] = br
        return br

    @property
    def state(self) -> str:
        return self._state

    def _maybe_close_window(self) -> None:
        if self._state == "open" and (time.monotonic() - self._opened_at) >= self._cooldown:
            self._state = "half_open"
            self._half_open_allowed = self._half_open_max

    def allow(self) -> bool:
        """Return True if a request may be attempted, else False (fail fast)."""
        self._maybe_close_window()
        if self._state == "closed":
            return True
        if self._state == "half_open":
            return self._half_open_allowed > 0
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == "half_open":
            self._state = "open"
            self._opened_at = time.monotonic()
            return
        if self._failures >= self._failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()

    async def call(self, coro_fn: Callable[[], Awaitable[Any]]) -> Any:
        """Run ``coro_fn`` under the breaker, raising ``CircuitOpen`` on open."""
        if not self.allow():
            raise CircuitOpen(self)
        try:
            result = await coro_fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result


class CircuitOpen(Exception):
    """Raised when a circuit breaker is open and the call is rejected."""


# ---------------------------------------------------------------------------
# Rate limiter (in-memory token bucket, per key)
# ---------------------------------------------------------------------------


class RateLimiter:
    """
    Per-key token-bucket rate limiter.

    Suitable for a single process / single host. For multi-node deployments a
    shared store (Redis) would be dropped in here without changing callers.
    """

    def __init__(
        self,
        *,
        rate: float = 10.0,
        capacity: float = 20.0,
        max_keys: int = 8192,
    ) -> None:
        self._rate = rate
        self._capacity = capacity
        self._max_keys = max_keys
        self._buckets: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    def _refill(self, bucket: list[float]) -> None:
        now = time.monotonic()
        tokens, last = bucket[0], bucket[1]
        elapsed = now - last
        tokens = min(self._capacity, tokens + elapsed * self._rate)
        bucket[0], bucket[1] = tokens, now

    async def consume(self, key: str, cost: float = 1.0) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    # At capacity: degrade open rather than block forever.
                    return True
                bucket = [self._capacity, time.monotonic()]
                self._buckets[key] = bucket
            self._refill(bucket)
            if bucket[0] >= cost:
                bucket[0] -= cost
                return True
            return False


# ---------------------------------------------------------------------------
# Request size limit middleware
# ---------------------------------------------------------------------------

DEFAULT_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB


class HTTPOverSize(Exception):
    """Internal signal raised when the body is too large (mapped to 413)."""


class RequestSizeLimit:
    """
    ASGI middleware that rejects requests whose body exceeds ``max_bytes``
    with ``413``, protecting the service from memory-exhaustion DoS.
    """

    def __init__(self, app: Any, max_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("method") in ("GET", "HEAD", "OPTIONS", "DELETE"):
            await self.app(scope, receive, send)
            return

        total = 0
        max_bytes = self.max_bytes

        async def receive_limited() -> dict:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > max_bytes:
                    raise HTTPOverSize(max_bytes)
            return message

        await self.app(scope, receive_limited, send)


def http_over_size_handler(_: Request, exc: HTTPOverSize) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"detail": f"Request body too large (max {exc.args[0]} bytes)"},
    )
