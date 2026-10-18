"""Serve the built dashboard and API from one local network address."""
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.responses import PlainTextResponse


class DashboardFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or path.startswith("assets/") or Path(path).suffix:
                return PlainTextResponse(error.detail, status_code=error.status_code)
            response = await super().get_response("index.html", scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        return response


class LocalDashboard:
    def __init__(self, api, directory):
        self.api = api
        self.files = DashboardFiles(directory=directory)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/sw.js":
            # Migrate old local PWA installs to network-served dashboard builds.
            # New local builds do not register a worker, so this runs only once.
            script = """self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', e => e.waitUntil((async () => {
  const names = await caches.keys();
  await Promise.all(names.filter(n => n.startsWith('workbox-')).map(n => caches.delete(n)));
  await self.registration.unregister();
  const pages = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
  await Promise.all(pages.map(page => page.navigate(page.url)));
})()));"""
            response = PlainTextResponse(script, media_type="application/javascript", headers={"Cache-Control": "no-store"})
            await response(scope, receive, send)
            return
        if scope["type"] == "lifespan" or scope.get("path", "").startswith(("/api", "/docs", "/openapi.json")):
            await self.api(scope, receive, send)
        else:
            await self.files(scope, receive, send)


def create_app():
    from api.main import app
    return LocalDashboard(app, Path(__file__).resolve().parent.parent / "frontend" / "dist")
