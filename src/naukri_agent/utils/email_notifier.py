"""
Email alert notifier for the Naukri Agent.

Sends HTML-formatted failure alert emails via Gmail SMTP when any
task or scheduled cron job encounters an error. Reuses the existing
GMAIL_OTP_EMAIL / GMAIL_APP_PASSWORD credentials.

Features:
    - Rich HTML email with error type, traceback, timestamp, hostname
    - File-based cooldown to suppress duplicate alerts (default 15 min)
    - Graceful degradation: logs warnings but never crashes the agent
"""

from __future__ import annotations

import json
import platform
import smtplib
import time
import traceback
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_COOLDOWN_FILE = ".alert_cooldowns.json"


class EmailAlertNotifier:
    """Sends failure-alert emails via Gmail SMTP.

    Args:
        sender_email: Gmail address used as the SMTP sender (GMAIL_OTP_EMAIL).
        app_password: Gmail App Password (GMAIL_APP_PASSWORD).
        recipient_email: The inbox to deliver alerts to. Falls back to
            *sender_email* when left blank.
        cooldown_minutes: Minimum gap (in minutes) between alerts that share
            the same *task_name*. Set to ``0`` to disable the cooldown.
        cooldown_dir: Directory in which the cooldown state file is stored.
    """

    def __init__(
        self,
        sender_email: str,
        app_password: str,
        recipient_email: str = "",
        cooldown_minutes: int = 15,
        cooldown_dir: str | Path = "data/logs",
    ) -> None:
        self._sender = sender_email
        self._password = app_password
        self._recipient = recipient_email or sender_email
        self._cooldown_seconds = cooldown_minutes * 60
        self._cooldown_path = Path(cooldown_dir) / _COOLDOWN_FILE
        self._cooldown_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def send_alert(
        self,
        task_name: str,
        exception: BaseException,
        extra_context: str = "",
    ) -> bool:
        """Send an alert email for *exception* that occurred in *task_name*.

        Returns ``True`` if an email was actually sent, ``False`` if it was
        suppressed by the cooldown or if sending failed.  This method is
        intentionally *fire-and-forget*; it never raises.
        """
        try:
            if not self._has_credentials():
                logger.warning(
                    "Email alert skipped — SMTP credentials (GMAIL_OTP_EMAIL / "
                    "GMAIL_APP_PASSWORD) are not configured."
                )
                return False

            if self._is_cooled_down(task_name):
                logger.info(
                    f"Email alert suppressed for '{task_name}' — cooldown active "
                    f"({self._cooldown_seconds // 60} min window)."
                )
                return False

            subject, html_body = self._build_email(task_name, exception, extra_context)
            self._smtp_send(subject, html_body)
            self._update_cooldown(task_name)

            logger.info(f"Alert email sent to {self._recipient} for task '{task_name}'.")
            return True

        except Exception as send_err:
            # Never crash the agent because of an alert failure.
            logger.warning(f"Failed to send alert email: {send_err}")
            return False

    # ------------------------------------------------------------------
    # Email construction
    # ------------------------------------------------------------------
    def _build_email(
        self,
        task_name: str,
        exception: BaseException,
        extra_context: str,
    ) -> tuple[str, str]:
        """Return (subject, html_body) for the alert."""
        error_type = type(exception).__qualname__
        error_msg = str(exception)
        tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
        tb_text = "".join(tb)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        host = platform.node() or "unknown"

        subject = f"🚨 Naukri Agent Alert — {task_name} failed ({error_type})"

        html_body = f"""\
<html>
<head>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #eaeaea; padding: 24px; }}
  .container {{ max-width: 680px; margin: 0 auto; background: #16213e; border-radius: 12px; padding: 28px; border: 1px solid #0f3460; }}
  h1 {{ color: #e94560; font-size: 22px; margin-top: 0; }}
  .meta-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
  .meta-table td {{ padding: 8px 12px; border-bottom: 1px solid #0f3460; font-size: 14px; }}
  .meta-table td:first-child {{ color: #a3bded; font-weight: 600; width: 140px; }}
  .error-box {{ background: #1a1a2e; border: 1px solid #e94560; border-radius: 8px; padding: 16px; margin: 16px 0; }}
  .error-type {{ color: #e94560; font-weight: 700; font-size: 16px; }}
  .error-msg {{ color: #f5c542; margin-top: 8px; font-size: 14px; word-break: break-word; }}
  .traceback {{ background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 16px 0;
                font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; color: #c9d1d9;
                white-space: pre-wrap; word-break: break-all; overflow-x: auto; max-height: 400px; }}
  .context {{ background: #1a1a2e; border: 1px solid #0f3460; border-radius: 8px; padding: 14px; margin: 16px 0;
              font-size: 13px; color: #a3bded; }}
  .footer {{ text-align: center; font-size: 12px; color: #555; margin-top: 24px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🚨 Naukri Agent — Task Failure Alert</h1>

  <table class="meta-table">
    <tr><td>Task</td><td><strong>{task_name}</strong></td></tr>
    <tr><td>Timestamp</td><td>{now}</td></tr>
    <tr><td>Host</td><td>{host}</td></tr>
    <tr><td>Recipient</td><td>{self._recipient}</td></tr>
  </table>

  <div class="error-box">
    <div class="error-type">{error_type}</div>
    <div class="error-msg">{self._escape_html(error_msg)}</div>
  </div>

  {"<div class='context'><strong>Additional Context:</strong><br/>" + self._escape_html(extra_context) + "</div>" if extra_context else ""}

  <details>
    <summary style="cursor:pointer; color:#a3bded; font-weight:600; margin: 12px 0;">
      📋 Full Traceback (click to expand)
    </summary>
    <div class="traceback">{self._escape_html(tb_text)}</div>
  </details>

  <div class="footer">
    Sent by <strong>Naukri AI Agent Monitoring</strong> • Auto-generated alert
  </div>
</div>
</body>
</html>"""

        return subject, html_body

    # ------------------------------------------------------------------
    # SMTP transport
    # ------------------------------------------------------------------
    def _smtp_send(self, subject: str, html_body: str) -> None:
        """Send the email synchronously via Gmail SMTP with STARTTLS."""
        msg = MIMEMultipart("alternative")
        msg["From"] = self._sender
        msg["To"] = self._recipient
        msg["Subject"] = subject

        # Plain-text fallback
        plain = (
            f"Naukri Agent Alert\n\n"
            f"A task has failed. Please check the HTML version of this "
            f"email for full details.\n\nSubject: {subject}"
        )
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self._sender, self._password)
            server.sendmail(self._sender, [self._recipient], msg.as_string())

    # ------------------------------------------------------------------
    # Cooldown logic
    # ------------------------------------------------------------------
    def _is_cooled_down(self, task_name: str) -> bool:
        """Return ``True`` if *task_name* is within its cooldown window."""
        if self._cooldown_seconds <= 0:
            return False
        cooldowns = self._load_cooldowns()
        last_sent = cooldowns.get(task_name, 0)
        return (time.time() - last_sent) < self._cooldown_seconds

    def _update_cooldown(self, task_name: str) -> None:
        """Record the current time as the last alert for *task_name*."""
        cooldowns = self._load_cooldowns()
        cooldowns[task_name] = time.time()
        try:
            with open(self._cooldown_path, "w", encoding="utf-8") as f:
                json.dump(cooldowns, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not write cooldown state: {e}")

    def _load_cooldowns(self) -> dict[str, float]:
        """Load cooldown state from the JSON file."""
        if not self._cooldown_path.exists():
            return {}
        try:
            with open(self._cooldown_path, encoding="utf-8") as f:
                data = json.load(f)
            return {k: float(v) for k, v in data.items()}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _has_credentials(self) -> bool:
        """Return ``True`` if both SMTP credentials are available."""
        return bool(self._sender and self._password)

    @staticmethod
    def _escape_html(text: str) -> str:
        """Minimal HTML escaping for safe embedding in the email body."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
