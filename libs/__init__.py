"""
Shared library for the Naukri microservice platform.

Holds cross-cutting concerns used by every service:
- Database engine factory (URL-driven; SQLite for local dev, Postgres for compose)
- Typed HTTP client for service-to-service calls
- A helper to build a FastAPI service app with a common lifespan
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
