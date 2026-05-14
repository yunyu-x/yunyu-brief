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

    def __init__(self, address: str, app_password: str, debug: bool = False):
        self.address = address
        self.app_password = app_password
        self.debug = debug

    def send(self, briefing: DailyBriefing, html_content: str, text_content: str) -> None:
        """Send briefing email to self."""
        subject = f"\U0001f4ec \u6bcf\u65e5\u7b80\u62a5 \u00b7 {briefing.date}"

        if self.debug:
            logger.debug(f"[SMTP] ─── Preparing email ───")
            logger.debug(f"[SMTP]   Host: {self.SMTP_HOST}:{self.SMTP_PORT} (SSL)")
            logger.debug(f"[SMTP]   From: {self.address}")
            logger.debug(f"[SMTP]   To: {self.address}")
            logger.debug(f"[SMTP]   Subject: {subject}")
            logger.debug(f"[SMTP]   HTML body: {len(html_content)} chars")
            logger.debug(f"[SMTP]   Text body: {len(text_content)} chars")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.address
        msg["To"] = self.address

        # Attach plain text and HTML versions
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        if self.debug:
            logger.debug(f"[SMTP]   Total MIME message size: {len(msg.as_string())} bytes")

        try:
            if self.debug:
                logger.debug(f"[SMTP] Connecting to {self.SMTP_HOST}:{self.SMTP_PORT}...")

            with smtplib.SMTP_SSL(self.SMTP_HOST, self.SMTP_PORT) as server:
                if self.debug:
                    logger.debug("[SMTP] ✅ Connected (SSL)")
                    logger.debug(f"[SMTP] Logging in as {self.address[:3]}***...")

                server.login(self.address, self.app_password)

                if self.debug:
                    logger.debug("[SMTP] ✅ Login successful")
                    logger.debug("[SMTP] Sending message...")

                server.sendmail(self.address, self.address, msg.as_string())

                if self.debug:
                    logger.debug("[SMTP] ✅ Message sent successfully")

            logger.info(f"Briefing email sent successfully: {subject}")

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            if self.debug:
                logger.debug(f"[SMTP] ❌ Auth error code: {e.smtp_code}")
                logger.debug(f"[SMTP] ❌ Auth error message: {e.smtp_error}")
                logger.debug("[SMTP] 💡 Check: Is App Password correct? Is 2-Step Verification enabled?")
            raise

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            if self.debug:
                logger.debug(f"[SMTP] ❌ SMTP exception: {type(e).__name__}: {e}")
            raise

        except Exception as e:
            logger.error(f"Failed to send briefing email: {e}")
            if self.debug:
                logger.debug(f"[SMTP] ❌ Unexpected error: {type(e).__name__}: {e}")
                import traceback
                logger.debug(f"[SMTP] ❌ Traceback:\n{traceback.format_exc()}")
            raise
