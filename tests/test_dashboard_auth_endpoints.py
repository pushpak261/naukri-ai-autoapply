"""HTTP-level regressions for login and refresh session ownership."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.deps import state
from api.routes import auth


class AuthEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_settings = state.settings
        state.settings = SimpleNamespace(
            data_dir=Path(self.directory.name),
            jwt_secret="test-signing-secret-with-at-least-32-bytes",
            jwt_encryption_key="test-encryption-secret",
            naukri=SimpleNamespace(email="operator@example.com", password="configured-password"),
        )
        app = FastAPI()
        app.include_router(auth.router)
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()
        state.settings = self.previous_settings
        self.directory.cleanup()

    async def test_valid_login_returns_token_and_can_refresh(self):
        response = await self.client.post("/api/auth/login", json={
            "email": "operator@example.com", "password": "configured-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["access_token"])
        self.assertEqual((await self.client.post("/api/auth/refresh")).status_code, 200)

    async def test_wrong_password_cannot_replace_operator_credentials(self):
        response = await self.client.post("/api/auth/login", json={
            "email": "operator@example.com", "password": "wrong-password",
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(state.settings.naukri.password, "configured-password")

    async def test_anonymous_refresh_cannot_use_server_saved_session(self):
        await self.client.post("/api/auth/login", json={
            "email": "operator@example.com", "password": "configured-password",
        })
        self.client.cookies.clear()
        self.assertEqual((await self.client.post("/api/auth/refresh")).status_code, 401)

    async def test_registration_honors_disable_and_keeps_operator_credentials(self):
        with patch.dict(os.environ, {"OPEN_REGISTRATION": "false"}):
            self.assertEqual((await self.client.post("/api/auth/register", json={
                "email": "other@example.com", "password": "other-password",
            })).status_code, 403)
        with patch.dict(os.environ, {"OPEN_REGISTRATION": "true"}):
            self.assertEqual((await self.client.post("/api/auth/register", json={
                "email": "other@example.com", "password": "other-password",
            })).status_code, 200)
            self.assertEqual(state.settings.naukri.email, "operator@example.com")
            self.assertEqual(state.settings.naukri.password, "configured-password")


if __name__ == "__main__":
    unittest.main()
