"""
Shared library for the Naukri microservice platform.

Re-exports the most-used helpers so services can do::

    from libs.common import make_service_app, ServiceClient, create_database_manager
"""

from __future__ import annotations

# Canonical service ports (kept in one place so services, the gateway, and
# docker-compose all agree).
SERVICE_PORTS = {
    "gateway": 8000,
    "auth": 8101,
    "config": 8102,
    "jobs": 8103,
    "resume": 8104,
    "applications": 8105,
    "ai": 8106,
    "agent": 8107,
    "data": 8108,
}

DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

from libs.common.auth import (  # noqa: E402
    resolve_jwt_secret,
    resolve_service_token,
    verify_access_token,
)
from libs.common.security import (  # noqa: E402
    decrypt_value,
    encrypt_value,
)
from libs.common.db import (  # noqa: E402
    create_database_manager,
    get_database_url,
    is_postgres,
)
from libs.common.http import AuthClient, ServiceClient  # noqa: E402
from libs.common.metrics import (  # noqa: E402
    AGENT_LAST_APPLY_TIMESTAMP,
    AGENT_LAST_RUN_TIMESTAMP,
    AGENT_RUNNING,
    CIRCUIT_BREAKER_OPEN,
    SERVER_ERRORS,
    MetricsMiddleware,
    metrics_response,
)
from libs.common.resilience import (  # noqa: E402
    CircuitBreaker,
    CircuitOpen,
    RateLimiter,
    RequestSizeLimit,
    async_retry,
)
from libs.common.service import make_service_app  # noqa: E402

__all__ = [
    "SERVICE_PORTS",
    "DEFAULT_CORS_ORIGINS",
    "create_database_manager",
    "get_database_url",
    "is_postgres",
    "ServiceClient",
    "AuthClient",
    "make_service_app",
    "resolve_jwt_secret",
    "resolve_service_token",
    "verify_access_token",
    "decrypt_value",
    "encrypt_value",
    "CircuitBreaker",
    "CircuitOpen",
    "RateLimiter",
    "RequestSizeLimit",
    "async_retry",
    "MetricsMiddleware",
    "metrics_response",
    "SERVER_ERRORS",
    "CIRCUIT_BREAKER_OPEN",
    "AGENT_LAST_RUN_TIMESTAMP",
    "AGENT_LAST_APPLY_TIMESTAMP",
    "AGENT_RUNNING",
    "AGENT_BLOCKED",
]
