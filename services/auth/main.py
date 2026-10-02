"""Auth Service â€” accounts, login, registration, API keys."""

from __future__ import annotations

from api.routes import accounts as accounts_router
from api.routes import auth as auth_router
from libs.common import make_service_app

app = make_service_app(
    name="auth-service",
    routers=[auth_router, accounts_router],
)

if __name__ == "__main__":
    from libs.common import serve

    serve(app, port=8101)
