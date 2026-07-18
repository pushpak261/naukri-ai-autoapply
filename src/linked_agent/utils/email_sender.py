"""
Utility for sending email reports (e.g. external jobs list) via SMTP.
"""

import html as _html
import smtplib
from email.message import EmailMessage
from datetime import datetime
import typing

if typing.TYPE_CHECKING:
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job

from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


def send_external_jobs_email(
    jobs_data: list[tuple["Job", str | None, str, str]], settings: "Settings"
) -> None:
    """
    Send an email containing a list of external/failed jobs to apply to manually.

    Args:
        jobs_data: List of tuples containing (Job, external_url, status, error_message)
        settings: Application settings containing email configuration
    """
    if not jobs_data:
        logger.info("No jobs to email.")
        return

    external_count = sum(1 for _, _, s, _ in jobs_data if s == "skipped_external")
    other_count = sum(1 for _, _, s, _ in jobs_data if s != "skipped_external")
    total = len(jobs_data)

    sender_email = settings.linkedin.gmail_otp_email
    app_password = settings.linkedin.gmail_app_password
    recipient = settings.application.email_recipient or sender_email

    if not sender_email or not app_password:
        logger.warning(
            "Cannot send email: gmail_otp_email or gmail_app_password is not configured."
        )
        return

    logger.info(f"Sending email report for {total} jobs ({external_count} external, {other_count} other) to {recipient}...")

    msg = EmailMessage()
    timestamp = datetime.now().strftime("%Y-%m-%d")
    msg["Subject"] = (
        f"[{timestamp}] LinkedIn Agent Report - {total} Jobs Need Attention ({external_count} external, {other_count} other)"
    )
    msg["From"] = sender_email
    msg["To"] = recipient

    html_content = _build_html_report(jobs_data, settings)

    msg.set_content("Please enable HTML to view this email.")
    msg.add_alternative(html_content, subtype="html")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, app_password)
            smtp.send_message(msg)
        logger.info(f"Successfully sent job report email to {recipient}")
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {e}")


def _build_html_report(
    jobs_data: list[tuple["Job", str | None, str, str]], settings: "Settings"
) -> str:
    """Build the HTML report string without sending it (for local file fallback)."""
    external_count = sum(1 for _, _, s, _ in jobs_data if s == "skipped_external")
    other_count = sum(1 for _, _, s, _ in jobs_data if s != "skipped_external")
    total = len(jobs_data)

    status_colors = {
        "skipped_external": "#ffc107",
        "skipped_screening": "#17a2b8",
        "failed": "#dc3545",
        "uncertain": "#6f42c1",
    }

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #2c3e50;">LinkedIn Agent - Jobs Report</h2>
        <p>The bot processed jobs and {total} require manual attention:
           <strong>{external_count}</strong> external applications,
           <strong>{other_count}</strong> other issues (failed/screening/etc).</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
          <thead>
            <tr style="background-color: #f8f9fa;">
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">Status</th>
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">Role</th>
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">Company</th>
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">Location</th>
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">Apply Link</th>
            </tr>
          </thead>
          <tbody>
    """

    for job, ext_url, status, error_msg in jobs_data:
        apply_href = ext_url if ext_url else job.url
        title = _html.escape(job.title or "N/A")
        company = _html.escape(job.company or "N/A")
        location = _html.escape(job.location or "N/A")
        apply_href_escaped = _html.escape(apply_href, quote=True)
        color = status_colors.get(status, "#6c757d")

        display_status = status.replace("skipped_", "").replace("_", " ").title()
        if status == "failed":
            display_status = "Failed"
        display_status_escaped = _html.escape(display_status)

        html += f"""
            <tr>
              <td style="padding: 12px; border: 1px solid #ddd;">
                <span style="display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; color: #fff; background-color: {color};">{display_status_escaped}</span>
              </td>
              <td style="padding: 12px; border: 1px solid #ddd;"><strong>{title}</strong></td>
              <td style="padding: 12px; border: 1px solid #ddd;">{company}</td>
              <td style="padding: 12px; border: 1px solid #ddd;">{location}</td>
              <td style="padding: 12px; border: 1px solid #ddd;">
                <a href="{apply_href_escaped}" target="_blank" style="display: inline-block; padding: 6px 12px; background-color: #007bff; color: white; text-decoration: none; border-radius: 4px;">Apply</a>
              </td>
            </tr>
        """

    html += """
          </tbody>
        </table>
        <p style="margin-top: 30px; font-size: 12px; color: #777;">Generated by LinkedIn Agent</p>
      </body>
    </html>
    """
    return html
