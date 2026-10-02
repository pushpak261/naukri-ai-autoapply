"""Tests for the external-jobs email report helper."""

from types import SimpleNamespace

from src.naukri_agent.utils import email_sender as email_sender_mod
from src.naukri_agent.utils.email_sender import send_external_jobs_email


def _job(title="Dev", company="Acme", location="Pune", url="https://naukri.com/job/1"):
    return SimpleNamespace(title=title, company=company, location=location, url=url)


def _settings(sender="agent@gmail.com", app_password="pw", recipient=None):
    return SimpleNamespace(
        naukri=SimpleNamespace(gmail_otp_email=sender, gmail_app_password=app_password),
        application=SimpleNamespace(email_recipient=recipient),
    )


class _FakeSMTP:
    """Records everything the sender does, so tests can assert on it."""

    last = None

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.logged_in = None
        self.message = None
        type(self).last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.message = msg


class TestNoOpPaths:
    def test_empty_job_list_does_not_connect(self, monkeypatch):
        def explode(*a, **k):  # pragma: no cover - must never run
            raise AssertionError("SMTP must not be used for an empty job list")

        monkeypatch.setattr(email_sender_mod.smtplib, "SMTP_SSL", explode)
        send_external_jobs_email([], _settings())

    def test_missing_sender_does_not_connect(self, monkeypatch):
        def explode(*a, **k):  # pragma: no cover - must never run
            raise AssertionError("SMTP must not be used without a sender")

        monkeypatch.setattr(email_sender_mod.smtplib, "SMTP_SSL", explode)
        send_external_jobs_email([(_job(), None)], _settings(sender=""))

    def test_missing_app_password_does_not_connect(self, monkeypatch):
        def explode(*a, **k):  # pragma: no cover - must never run
            raise AssertionError("SMTP must not be used without an app password")

        monkeypatch.setattr(email_sender_mod.smtplib, "SMTP_SSL", explode)
        send_external_jobs_email([(_job(), None)], _settings(app_password=""))


class TestSending:
    def test_sends_report_with_all_jobs(self, monkeypatch):
        monkeypatch.setattr(email_sender_mod.smtplib, "SMTP_SSL", _FakeSMTP)

        send_external_jobs_email(
            [(_job(), "https://ats.example.com/1"), (_job(title="Sr Dev"), None)],
            _settings(recipient="ops@acme.com"),
        )

        smtp = _FakeSMTP.last
        assert smtp.host == "smtp.gmail.com"
        assert smtp.port == 465
        assert smtp.logged_in == ("agent@gmail.com", "pw")
        assert smtp.message["To"] == "ops@acme.com"
        assert smtp.message["From"] == "agent@gmail.com"
        assert "2 Jobs Require Manual Application" in smtp.message["Subject"]

        html = smtp.message.get_body(preferencelist=("html",)).get_content()
        assert "https://ats.example.com/1" in html
        # Second job has no external URL, so it must fall back to the Naukri URL.
        assert "https://naukri.com/job/1" in html
        assert "Sr Dev" in html

    def test_recipient_defaults_to_sender(self, monkeypatch):
        monkeypatch.setattr(email_sender_mod.smtplib, "SMTP_SSL", _FakeSMTP)

        send_external_jobs_email([(_job(), None)], _settings(recipient=None))

        assert _FakeSMTP.last.message["To"] == "agent@gmail.com"

    def test_missing_job_fields_render_as_na(self, monkeypatch):
        monkeypatch.setattr(email_sender_mod.smtplib, "SMTP_SSL", _FakeSMTP)

        send_external_jobs_email(
            [(_job(title=None, company=None, location=None), "https://x/y")],
            _settings(),
        )

        html = _FakeSMTP.last.message.get_body(preferencelist=("html",)).get_content()
        assert html.count("N/A") == 3

    def test_smtp_failure_is_swallowed(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("smtp down")

        monkeypatch.setattr(email_sender_mod.smtplib, "SMTP_SSL", boom)
        # Must not raise: a failed report email must not abort the run.
        send_external_jobs_email([(_job(), None)], _settings())
