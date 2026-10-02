"""Tests for the Gmail IMAP OTP provider.

IMAP is faked at the ``imaplib.IMAP4_SSL`` boundary so the polling loop,
multipart handling and timeout behaviour can be exercised without network.
"""

import email
import time

import pytest

from src.naukri_agent.utils import gmail_otp as gmail_mod
from src.naukri_agent.utils.gmail_otp import GmailOTPProvider, fetch_naukri_otp


def _raw_email(subject="Naukri OTP 123456", sender="no-reply@naukri.com", body="<p>Your OTP is 123456</p>"):
    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg.set_content(body)
    return msg.as_bytes()


class FakeIMAP:
    """Minimal IMAP4_SSL stand-in driven by a scripted list of messages."""

    instance = None

    def __init__(self, host, *args, **kwargs):
        self.host = host
        self.logged_in = None
        self.selected = None
        self.stored = []
        self.logged_out = False
        self.search_results = {"UNSEEN": [], "ALL": []}
        self.messages = {}
        type(self).instance = self

    # -- protocol surface -------------------------------------------------
    def login(self, user, password):
        self.logged_in = (user, password)
        return "OK", [b"logged in"]

    def select(self, mailbox):
        self.selected = mailbox
        return "OK", [b"1"]

    def search(self, _charset, criteria):
        return "OK", [self.search_results.get(criteria, b"")]

    def fetch(self, mail_id, _query):
        payload = self.messages.get(mail_id)
        if payload is None:
            return "NO", [None]
        return "OK", [(b"1", payload)]

    def store(self, mail_id, command, flags):
        self.stored.append((mail_id, command, flags))
        return "OK", [b"stored"]

    def logout(self):
        self.logged_out = True

    # -- helpers ----------------------------------------------------------
    def add(self, message_id: bytes, raw: bytes):
        self.messages[message_id] = raw


@pytest.fixture
def imap(monkeypatch):
    FakeIMAP.instance = None
    monkeypatch.setattr(gmail_mod.imaplib, "IMAP4_SSL", FakeIMAP)

    def build(messages=None, unseen=None, all_ids=None, store_fails=False):
        conn = FakeIMAP("imap.gmail.com")

        def factory(host, *a, **k):
            nonlocal conn
            return conn

        for mid, raw in (messages or {}).items():
            conn.add(mid, raw)
        if unseen is not None:
            conn.search_results["UNSEEN"] = b" ".join(unseen)
        if all_ids is not None:
            conn.search_results["ALL"] = b" ".join(all_ids)
        if store_fails:
            def boom(*a, **k):
                raise OSError("store failed")

            conn.store = boom

        monkeypatch.setattr(gmail_mod.imaplib, "IMAP4_SSL", factory)
        return conn

    return build


class TestOtpExtraction:
    def test_finds_otp_in_multipart_email(self, imap):
        imap(messages={b"1": _raw_email()}, unseen=[b"1"])

        provider = GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=1)
        assert provider._fetch_otp_sync() == "123456"

    def test_marks_email_as_seen(self, imap):
        conn = imap(messages={b"1": _raw_email()}, unseen=[b"1"])

        GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=1)._fetch_otp_sync()

        assert conn.stored and conn.stored[0][2] == "\\Seen"

    def test_falls_back_to_all_messages_when_no_unseen(self, imap):
        imap(messages={b"1": _raw_email()}, unseen=[], all_ids=[b"1"])

        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=1)._fetch_otp_sync() == "123456"

    def test_only_last_ten_messages_are_scanned(self, imap):
        ids = [str(i).encode() for i in range(1, 21)]
        imap(messages={}, unseen=[], all_ids=ids)

        start = time.time()
        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=0, poll_interval_seconds=0)._fetch_otp_sync() is None
        assert time.time() - start < 5

    def test_ignores_unrelated_senders(self, imap):
        imap(messages={b"1": _raw_email(subject="Your OTP", sender="spam@evil.com")}, unseen=[b"1"])

        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=0, poll_interval_seconds=0)._fetch_otp_sync() is None

    def test_ignores_naukri_mail_without_otp_keywords(self, imap):
        imap(messages={b"1": _raw_email(subject="Naukri profile update", body="nothing here")}, unseen=[b"1"])

        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=0, poll_interval_seconds=0)._fetch_otp_sync() is None

    @pytest.mark.parametrize("subject", ["Naukri OTP", "Naukri Verification", "Naukri one time password", "Naukri code"])
    def test_accepts_each_otp_keyword(self, imap, subject):
        imap(messages={b"1": _raw_email(subject=subject)}, unseen=[b"1"])

        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=1)._fetch_otp_sync() == "123456"

    def test_newest_email_wins(self, imap):
        imap(
            messages={
                b"1": _raw_email(subject="Naukri OTP 111111", body="code 111111"),
                b"2": _raw_email(subject="Naukri OTP 222222", body="code 222222"),
            },
            unseen=[b"1", b"2"],
        )

        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=1)._fetch_otp_sync() == "222222"

    def test_ignores_six_digit_run_inside_a_longer_number(self, imap):
        imap(messages={b"1": _raw_email(body="ref 1234567890 only")}, unseen=[b"1"])

        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=0, poll_interval_seconds=0)._fetch_otp_sync() is None

    def test_store_failure_does_not_lose_the_otp(self, imap):
        imap(messages={b"1": _raw_email()}, unseen=[b"1"], store_fails=True)

        assert GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=1)._fetch_otp_sync() == "123456"

    def test_fetch_failure_is_retried_then_times_out(self, monkeypatch):
        calls = []

        class FlakyIMAP:
            def __init__(self, host):
                calls.append(host)

            def login(self, *a):
                raise OSError("auth failed")

            def logout(self):
                pass

        monkeypatch.setattr(gmail_mod.imaplib, "IMAP4_SSL", FlakyIMAP)

        provider = GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=0, poll_interval_seconds=0)
        assert provider._fetch_otp_sync() is None
        # timeout_seconds=0 means the while loop body never runs.
        assert calls == []

    def test_connection_error_is_swallowed_and_polled(self, monkeypatch):
        attempts = []

        class SometimesDownIMAP:
            def __init__(self, host):
                attempts.append(host)
                if len(attempts) == 1:
                    raise OSError("connection refused")

            def login(self, *a):
                return "OK", [b""]

            def select(self, *a):
                return "OK", [b""]

            def search(self, *a):
                return "OK", [b""]

            def logout(self):
                pass

        monkeypatch.setattr(gmail_mod.imaplib, "IMAP4_SSL", SometimesDownIMAP)

        provider = GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=5, poll_interval_seconds=0)
        assert provider._fetch_otp_sync() is None
        assert len(attempts) > 1


class TestAsyncAndWrapper:
    async def test_retrieve_otp_runs_in_a_thread(self, imap):
        imap(messages={b"1": _raw_email()}, unseen=[b"1"])

        provider = GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=1)
        assert await provider.retrieve_otp() == "123456"

    async def test_retrieve_otp_returns_none_on_timeout(self, imap):
        imap(messages={}, unseen=[], all_ids=[])

        provider = GmailOTPProvider("me@gmail.com", "pw", timeout_seconds=0)
        assert await provider.retrieve_otp() is None

    def test_module_wrapper_delegates_to_provider(self, imap):
        imap(messages={b"1": _raw_email()}, unseen=[b"1"])

        assert fetch_naukri_otp("me@gmail.com", "pw", timeout_seconds=1) == "123456"
