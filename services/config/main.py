"""Config Service — config.yaml / linkedin config management."""

from __future__ import annotations

from api.routes import config as config_router
from libs.common import make_service_app

app = make_service_app(
    name="config-service",
    routers=[config_router],
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8102)
