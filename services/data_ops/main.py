"""Data & Ops Service — logs, metrics, backups, export/import, bulk clear."""

from __future__ import annotations

from api.routes import data as data_router
from libs.common import make_service_app

app = make_service_app(
    name="data-service",
    routers=[data_router],
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8108)
