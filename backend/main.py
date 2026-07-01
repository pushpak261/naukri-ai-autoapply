"""FastAPI application factory for the Naukri Agent web dashboard."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import applications, config, health, jobs, runs


def create_app() -> FastAPI:
    app = FastAPI(
        title="Naukri AI Agent API",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = FastAPI()
    api.include_router(health.router)
    api.include_router(runs.router)
    api.include_router(jobs.router)
    api.include_router(applications.router)
    api.include_router(config.router)

    app.mount("/api/v1", api)
    return app


app = create_app()
