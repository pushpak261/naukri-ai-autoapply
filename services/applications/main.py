"""Application & Analytics Service â€” applications, run logs, stats, analytics."""

from __future__ import annotations

from api.routes import applications as applications_router
from api.routes import stats as stats_router
from libs.common import make_service_app

app = make_service_app(
    name="applications-service",
    routers=[applications_router, stats_router],
    resolve_active_account=True,
)

if __name__ == "__main__":
    from libs.common import serve

    serve(app, port=8105)
