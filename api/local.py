"""Serve the built dashboard and API from one local network address."""
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.responses import PlainTextResponse


class DashboardFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or path.startswith("assets/") or Path(path).suffix:
                return PlainTextResponse(error.detail, status_code=error.status_code)
            return await super().get_response("index.html", scope)


class LocalDashboard:
    def __init__(self, api, directory):
        self.api = api
        self.files = DashboardFiles(directory=directory)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan" or scope.get("path", "").startswith(("/api", "/docs", "/openapi.json")):
            await self.api(scope, receive, send)
        else:
            await self.files(scope, receive, send)


def create_app():
    from api.main import app
    return LocalDashboard(app, Path(__file__).resolve().parent.parent / "frontend" / "dist")
