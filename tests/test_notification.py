"""Tests for email notification helpers."""

from types import SimpleNamespace

import pytest

from src.naukri_agent.utils import notification as notification_mod
from src.naukri_agent.utils.notification import (
    _get_recipient,
    _should_notify,
    notify_application_failed,
    notify_application_submitted,
    notify_match_found,
    notify_scam_detected,
    send_notification,
)


def _settings(**overrides):
    """Build a minimal settings object shaped like the agent's settings."""
    app = SimpleNamespace(
        email_notifications_enabled=overrides.get("enabled", True),
        notify_on_apply=overrides.get("notify_on_apply", True),
        notify_on_failure=overrides.get("notify_on_failure", True),
        notify_on_scam=overrides.get("notify_on_scam", True),
        notify_on_match=overrides.get("notify_on_match", True),
        email_recipient=overrides.get("email_recipient"),
    )
    naukri = SimpleNamespace(
        gmail_otp_email=overrides.get("sender", "agent@gmail.com"),
        gmail_app_password=overrides.get("app_password", "app-password"),
    )
    return SimpleNamespace(application=app, naukri=naukri)


class TestShouldNotify:
    def test_disabled_globally_returns_false(self):
        assert _should_notify(_settings(enabled=False), "application.created") is False

    @pytest.mark.parametrize(
        ("event", "flag"),
        [
            ("application.created", "notify_on_apply"),
            ("application.failed", "notify_on_failure"),
            ("scam.detected", "notify_on_scam"),
            ("match.found", "notify_on_match"),
        ],
    )
    def test_each_event_maps_to_its_flag(self, event, flag):
        assert _should_notify(_settings(), event) is True
        assert _should_notify(_settings(**{flag: False}), event) is False

    def test_unknown_event_returns_false(self):
        assert _should_notify(_settings(), "something.else") is False


class TestGetRecipient:
    def test_prefers_explicit_recipient(self):
        assert _get_recipient(_settings(email_recipient="ops@acme.com")) == "ops@acme.com"

    def test_falls_back_to_sender(self):
        assert _get_recipient(_settings()) == "agent@gmail.com"

    def test_no_sender_returns_none(self):
        assert _get_recipient(_settings(sender="")) is None

    def test_no_app_password_returns_none(self):
        assert _get_recipient(_settings(app_password="")) is None


class TestSendNotification:
    async def test_returns_false_when_event_disabled(self):
        assert await send_notification(_settings(enabled=False), "application.created", "s", "<p/>") is False

    async def test_returns_false_when_smtp_not_configured(self):
        settings = _settings(app_password="")
        assert await send_notification(settings, "application.created", "s", "<p/>") is False

    async def test_sends_via_smtp_ssl(self, monkeypatch):
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port):
                sent["host"] = host
                sent["port"] = port

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def login(self, user, password):
                sent["login"] = (user, password)

            def send_message(self, msg):
                sent["subject"] = msg["Subject"]
                sent["to"] = msg["To"]

        monkeypatch.setattr(notification_mod.smtplib, "SMTP_SSL", FakeSMTP)

        ok = await send_notification(
            _settings(email_recipient="ops@acme.com"),
            "application.created",
            "Applied",
            "<p>hi</p>",
        )

        assert ok is True
        assert sent["host"] == "smtp.gmail.com"
        assert sent["port"] == 465
        assert sent["login"] == ("agent@gmail.com", "app-password")
        assert sent["subject"] == "[Naukri Agent] Applied"
        assert sent["to"] == "ops@acme.com"

    async def test_smtp_failure_is_swallowed(self, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(notification_mod.smtplib, "SMTP_SSL", boom)

        ok = await send_notification(_settings(), "application.created", "s", "<p/>")
        assert ok is False


class TestNotificationHelpers:
    @pytest.fixture(autouse=True)
    def _capture(self, monkeypatch):
        """Capture the (event, subject, html) triple passed to send_notification."""
        self.calls = []

        async def fake_send_notification(settings, event, subject, html_body):
            self.calls.append((event, subject, html_body))
            return True

        monkeypatch.setattr(
            notification_mod, "send_notification", fake_send_notification
        )

    async def test_application_submitted(self):
        assert await notify_application_submitted(_settings(), "Dev", "Acme", 91.4, "2026-01-01") is True
        event, subject, html = self.calls[0]
        assert event == "application.created"
        assert subject == "Applied to Dev @ Acme"
        assert "91%" in html
        assert "2026-01-01" in html

    async def test_application_failed(self):
        assert await notify_application_failed(_settings(), "Dev", "Acme", "timeout") is True
        event, subject, html = self.calls[0]
        assert event == "application.failed"
        assert subject == "Application Failed: Dev @ Acme"
        assert "timeout" in html

    async def test_scam_detected_lists_reasons(self):
        assert await notify_scam_detected(_settings(), "Dev", "Acme", 88.0, ["a", "b"]) is True
        event, subject, html = self.calls[0]
        assert event == "scam.detected"
        assert subject == "Scam Alert: Dev @ Acme"
        assert "<li>a</li><li>b</li>" in html
        assert "88%" in html

    async def test_match_found_includes_score_and_url(self):
        assert await notify_match_found(_settings(), "Dev", "Acme", 95.2, "https://x/y") is True
        event, subject, html = self.calls[0]
        assert event == "match.found"
        assert subject == "High Match: Dev @ Acme (95%)"
        assert 'href="https://x/y"' in html
