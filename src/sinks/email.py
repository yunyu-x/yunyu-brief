"""Email sink — sends briefing via Gmail SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.models import DailyBriefing

logger = logging.getLogger(__name__)


class EmailSink:
    """Send the daily briefing via Gmail SMTP.

    Uses SSL on port 465 with App Password authentication.
    Sends to self (same address as sender).
    """

    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 465

    def __init__(self, address: str, app_password: str):
        self.address = address
        self.app_password = app_password

    def send(self, briefing: DailyBriefing, html_content: str, text_content: str) -> None:
        """Send briefing email to self."""
        subject = f"\U0001f4ec \u6bcf\u65e5\u7b80\u62a5 \u00b7 {briefing.date}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.address
        msg["To"] = self.address

        # Attach plain text and HTML versions
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            with smtplib.SMTP_SSL(self.SMTP_HOST, self.SMTP_PORT) as server:
                server.login(self.address, self.app_password)
                server.sendmail(self.address, self.address, msg.as_string())
            logger.info(f"Briefing email sent successfully: {subject}")
        except Exception as e:
            logger.error(f"Failed to send briefing email: {e}")
            raise
