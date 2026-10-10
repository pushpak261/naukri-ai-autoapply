"""Regression coverage for dashboard bearer and EventSource authentication."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from starlette.requests import Request

from api.auth.dashboard import accepts_dashboard_token
from api.auth.jwt import (
    create_access_token,
    create_refresh_token,
    load_refresh_token,
    save_refresh_token,
)


class DashboardAuthTests(unittest.TestCase):
    secret = "test-signing-secret-with-at-least-32-bytes"
    key = "operator-api-key"

    def request(self, path="/api/stats", bearer="", query=""):
        return Request({
            "type": "http", "method": "GET", "path": path,
            "headers": [(b"authorization", f"Bearer {bearer}".encode())] if bearer else [],
            "query_string": query.encode(),
        })

    def test_accepts_operator_key_and_signed_dashboard_token(self):
        token = create_access_token("operator@example.com", self.secret)
        for bearer in (self.key, token):
            self.assertTrue(accepts_dashboard_token(self.request(bearer=bearer), self.key, self.secret))

    def test_rejects_missing_wrong_or_refresh_tokens(self):
        for bearer in ("", "bad", create_refresh_token("operator@example.com", self.secret),
                       create_access_token("operator@example.com", "different-secret-with-at-least-32-bytes")):
            self.assertFalse(accepts_dashboard_token(self.request(bearer=bearer), self.key, self.secret))

    def test_query_tokens_are_limited_to_live_log_endpoints(self):
        token = create_access_token("operator@example.com", self.secret)
        for path in ("/api/agent/output/stream", "/api/multi/output/stream"):
            self.assertTrue(accepts_dashboard_token(self.request(path, query=f"token={token}"), self.key, self.secret))
        self.assertFalse(accepts_dashboard_token(self.request(query=f"token={token}"), self.key, self.secret))

    def test_encrypted_refresh_token_survives_recreating_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SimpleNamespace(data_dir=Path(directory), jwt_secret=self.secret, jwt_encryption_key="")
            token = create_refresh_token("operator@example.com", self.secret)
            save_refresh_token(settings, token)
            restarted = SimpleNamespace(**vars(settings))
            self.assertEqual(load_refresh_token(restarted), token)


if __name__ == "__main__":
    unittest.main()
