"""
HTTP helpers for service-to-service communication.

``ServiceClient`` is a thin async wrapper around ``httpx`` used by services
that need to call another service (e.g. the Agent Orchestrator calling the
AI Service, or the Gateway proxying requests). It provides:

  * a shared, pooled ``httpx.AsyncClient`` (no per-call connection handshake),
  * built-in retry-with-backoff on transient transport errors,
  * circuit breaking per upstream so a sick dependency fails fast,
  * propagation of ``Authorization``, ``X-Request-ID`` and ``traceparent``.
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any

import httpx

from libs.common import SERVICE_PORTS
from libs.common.resilience import CircuitBreaker, CircuitOpen, async_retry


class ServiceClient:
    """Async REST client for talking to another microservice."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_connections: int = 100,
        max_keepalive: int = 20,
        breaker_name: str | None = None,
        request_id: str | None = None,
        traceparent: str | None = None,
        auth: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._breaker_name = breaker_name
        self._request_id = request_id
        self._traceparent = traceparent
        self._auth = auth
        limits = httpx.Limits(
            max_connections=max_connections, max_keepalive_connections=max_keepalive
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            limits=limits,
        )

    @classmethod
    def for_service(
        cls,
        name: str,
        *,
        timeout: float = 30.0,
        breaker_name: str | None = None,
        request_id: str | None = None,
        traceparent: str | None = None,
        auth: str | None = None,
    ) -> ServiceClient:
        """Resolve a service URL from ``<NAME>_SERVICE_URL`` or default localhost."""
        env_key = f"{name.upper()}_SERVICE_URL"
        url = os.environ.get(env_key) or f"http://localhost:{SERVICE_PORTS[name]}"
        return cls(
            url,
            timeout=timeout,
            breaker_name=breaker_name or name,
            request_id=request_id,
            traceparent=traceparent,
            auth=auth,
        )

    def _extra_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._auth:
            headers["Authorization"] = self._auth
        if self._request_id:
            headers["X-Request-ID"] = self._request_id
        if self._traceparent:
            headers["traceparent"] = self._traceparent
        return headers

    @async_retry(max_attempts=3, initial=0.2, max_wait=3.0)
    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        breaker = CircuitBreaker.for_upstream(self._breaker_name) if self._breaker_name else None
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self._extra_headers())

        async def _do() -> httpx.Response:
            return await self._client.request(method, path, headers=headers, **kwargs)

        if breaker is not None:
            try:
                return await breaker.call(_do)
            except CircuitOpen:
                raise ServiceUnavailable(self.base_url) from None
        return await _do()

    async def get(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("POST", path, **kw)

    async def put(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("PUT", path, **kw)

    async def delete(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("DELETE", path, **kw)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ServiceClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


class ServiceUnavailable(Exception):
    """Raised when the upstream circuit breaker is open."""


class AuthClient:
    """Lightweight client for verifying credentials against the Auth Service."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._client = ServiceClient(base_url, breaker_name="auth", auth=api_key)

    @classmethod
    def for_auth_service(cls, api_key: str | None = None) -> AuthClient:
        return cls(ServiceClient.for_service("auth").base_url, api_key)

    async def verify_token(self, token: str) -> dict | None:
        """Return the user payload if the bearer token is valid, else ``None``."""
        try:
            resp = await self._client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"} if token else {},
            )
        except httpx.HTTPError:
            return None
        if resp.status_code == 200:
            return resp.json()
        return None

    async def close(self) -> None:
        await self._client.close()
