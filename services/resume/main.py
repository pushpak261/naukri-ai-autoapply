"""Resume & Profile Service â€” resume upload/parse, profile, optimization."""

from __future__ import annotations

from api.routes import resume as resume_router
from api.routes import resume_optimization as resume_optimization_router
from libs.common import make_service_app

app = make_service_app(
    name="resume-service",
    routers=[resume_router, resume_optimization_router],
)

if __name__ == "__main__":
    from libs.common import serve

    serve(app, port=8104)
