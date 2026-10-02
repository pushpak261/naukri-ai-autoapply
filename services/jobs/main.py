"""Job & Search Service â€” job discovery, listings, market intelligence."""

from __future__ import annotations

from api.routes import jobs as jobs_router
from api.routes import market_intel as market_intel_router
from libs.common import make_service_app

app = make_service_app(
    name="jobs-service",
    routers=[jobs_router, market_intel_router],
    resolve_active_account=True,
)

if __name__ == "__main__":
    from libs.common import serve

    serve(app, port=8103)
