"""Authenticate dashboard requests, including browser EventSource streams."""

import secrets

from api.auth.jwt import verify_access_token


def accepts_dashboard_token(request, api_key: str, jwt_secret: str) -> bool:
    authorization = request.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    # Native EventSource cannot set Authorization. Restrict query tokens to SSE.
    if not token and request.url.path in {
        "/api/agent/output/stream", "/api/multi/output/stream"
    }:
        token = request.query_params.get("token", "")
    if not token:
        return False
    if secrets.compare_digest(token, api_key):
        return True
    payload = verify_access_token(token, jwt_secret)
    return bool(payload and payload.get("sub"))
