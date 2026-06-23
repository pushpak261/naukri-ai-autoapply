"""
Utility for fetching Naukri.com login OTP from Gmail using IMAP.
"""

from __future__ import annotations

import contextlib
import email
import imaplib
import re
import time
from email.header import decode_header

from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_naukri_otp(
    gmail_email: str,
    app_password: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
) -> str | None:
    """
    Poll Gmail inbox via IMAP to find the latest Naukri login OTP.

    Args:
        gmail_email: User's Gmail email address.
        app_password: Gmail App Password (requires 2FA enabled on Google Account).
        timeout_seconds: How long to wait for the OTP email to arrive.
        poll_interval_seconds: Polling interval.

    Returns:
        The 6-digit OTP string if found, otherwise None.
    """
    start_time = time.time()
    logger.info("Connecting to Gmail IMAP to fetch Naukri OTP...")

    while time.time() - start_time < timeout_seconds:
        mail = None
        try:
            # Connect and log in
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(gmail_email, app_password)
            mail.select("INBOX")

            # Try to search for UNSEEN emails first to reduce load
            status, messages = mail.search(None, "UNSEEN")
            mail_ids = []
            if status == "OK" and messages[0]:
                mail_ids = messages[0].split()

            # If no unseen messages, fall back to searching all messages
            if not mail_ids:
                status, messages = mail.search(None, "ALL")
                if status == "OK" and messages[0]:
                    # Limit to the last 10 emails to avoid scanning a massive inbox
                    mail_ids = messages[0].split()[-10:]

            # Process from newest to oldest
            for mail_id in reversed(mail_ids):
                status, data = mail.fetch(mail_id, "(RFC822)")
                if status != "OK" or not data or not data[0]:
                    continue

                raw_email = data[0][1]
                if not isinstance(raw_email, bytes):
                    continue

                msg = email.message_from_bytes(raw_email)

                # Extract and decode subject
                subject_header = msg.get("Subject", "")
                subject = ""
                if subject_header:
                    decoded = decode_header(subject_header)
                    subject_parts = []
                    for subject_bytes, encoding in decoded:
                        if isinstance(subject_bytes, bytes):
                            try:
                                subject_parts.append(
                                    subject_bytes.decode(encoding or "utf-8", errors="ignore")
                                )
                            except Exception:
                                subject_parts.append(
                                    subject_bytes.decode("latin1", errors="ignore")
                                )
                        else:
                            subject_parts.append(str(subject_bytes))
                    subject = "".join(subject_parts)

                # Extract sender
                sender = str(msg.get("From", "")).lower()

                # We only want to process emails that are related to Naukri and contain OTP/Verification
                is_naukri = "naukri" in sender or "naukri" in subject.lower()
                has_otp_keywords = (
                    "otp" in subject.lower()
                    or "verification" in subject.lower()
                    or "one time password" in subject.lower()
                    or "code" in subject.lower()
                )

                if not (is_naukri and has_otp_keywords):
                    continue

                # Get email body content
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition", ""))
                        if "attachment" in content_disposition:
                            continue
                        if content_type in ("text/plain", "text/html"):
                            payload = part.get_payload(decode=True)
                            if isinstance(payload, bytes):
                                body += payload.decode("utf-8", errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        body = payload.decode("utf-8", errors="ignore")

                # Match exactly a 6-digit numeric pattern (typical Naukri OTP)
                # Naukri OTPs are typically 6-digit numbers. Let's make sure we find them.
                match = re.search(r"\b\d{6}\b", body)
                if match:
                    otp = match.group(0)
                    logger.info(f"Successfully retrieved Naukri OTP: {otp}")

                    # Mark the processed email as read
                    try:
                        mail.store(mail_id, "+FLAGS", "\\Seen")
                    except Exception as store_err:
                        logger.debug(f"Failed to mark email as seen: {store_err}")

                    mail.logout()
                    return otp

            # Log progress if we are still polling
            time_elapsed = int(time.time() - start_time)
            logger.info(
                f"Polling Gmail for OTP... ({time_elapsed}s elapsed, no matching OTP found yet)"
            )

        except Exception as e:
            logger.debug(f"Error checking Gmail IMAP (will retry): {e}")
        finally:
            if mail:
                with contextlib.suppress(Exception):
                    mail.logout()

        time.sleep(poll_interval_seconds)

    logger.warning("Timed out waiting for Naukri OTP email from Gmail.")
    return None
