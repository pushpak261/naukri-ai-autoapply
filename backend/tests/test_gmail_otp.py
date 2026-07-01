"""
Unit tests for the Gmail OTP parsing utility.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.naukri_agent.utils.gmail_otp import GmailOTPProvider, fetch_naukri_otp


def test_fetch_naukri_otp_success():
    """Test fetch_naukri_otp when it successfully connects and finds an OTP."""
    mock_imap = MagicMock()
    # Mock search to return message IDs
    mock_imap.search.return_value = ("OK", [b"1 2 3"])

    # Mock email fetching
    email_body = (
        b"From: info@naukri.com\r\n"
        b"Subject: OTP for Naukri Login\r\n\r\n"
        b"Hi User, your verification code is 884723. Do not share it."
    )
    mock_imap.fetch.return_value = ("OK", [(b"1 (RFC822)", email_body)])

    with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
        otp = fetch_naukri_otp(
            gmail_email="test@gmail.com",
            app_password="test_password",
            timeout_seconds=5,
            poll_interval_seconds=1,
        )

        assert otp == "884723"
        mock_imap.login.assert_called_once_with("test@gmail.com", "test_password")
        mock_imap.select.assert_called_with("INBOX")
        mock_imap.store.assert_called_once_with(b"3", "+FLAGS", "\\Seen")
        mock_imap.logout.assert_called()


def test_fetch_naukri_otp_timeout():
    """Test fetch_naukri_otp when no matching emails are found and it times out."""
    mock_imap = MagicMock()
    # Mock search to return no messages
    mock_imap.search.return_value = ("OK", [b""])

    with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
        otp = fetch_naukri_otp(
            gmail_email="test@gmail.com",
            app_password="test_password",
            timeout_seconds=2,
            poll_interval_seconds=1,
        )

        assert otp is None
        mock_imap.logout.assert_called()


def test_fetch_naukri_otp_ignore_non_naukri_emails():
    """Test that non-Naukri and non-OTP emails are ignored."""
    mock_imap = MagicMock()
    mock_imap.search.return_value = ("OK", [b"1"])

    # Email that is NOT from Naukri and doesn't contain OTP keywords
    email_body = (
        b"From: spam@advertise.com\r\n"
        b"Subject: Buy cheap products\r\n\r\n"
        b"Verify this random number: 123456"
    )
    mock_imap.fetch.return_value = ("OK", [(b"1 (RFC822)", email_body)])

    with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
        otp = fetch_naukri_otp(
            gmail_email="test@gmail.com",
            app_password="test_password",
            timeout_seconds=2,
            poll_interval_seconds=1,
        )

        assert otp is None
        mock_imap.store.assert_not_called()


async def test_gmail_otp_provider_success():
    """Test GmailOTPProvider when it successfully connects and finds an OTP."""
    mock_imap = MagicMock()
    mock_imap.search.return_value = ("OK", [b"1 2 3"])

    email_body = (
        b"From: info@naukri.com\r\n"
        b"Subject: OTP for Naukri Login\r\n\r\n"
        b"Hi User, your verification code is 884723. Do not share it."
    )
    mock_imap.fetch.return_value = ("OK", [(b"1 (RFC822)", email_body)])

    with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
        provider = GmailOTPProvider(
            gmail_email="test@gmail.com",
            app_password="test_password",
            timeout_seconds=5,
            poll_interval_seconds=1,
        )
        otp = await provider.retrieve_otp()

        assert otp == "884723"
        mock_imap.login.assert_called_once_with("test@gmail.com", "test_password")
        mock_imap.select.assert_called_with("INBOX")
        mock_imap.store.assert_called_once_with(b"3", "+FLAGS", "\\Seen")
        mock_imap.logout.assert_called()
