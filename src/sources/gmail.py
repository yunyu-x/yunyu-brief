"""Gmail IMAP source — fetches newsletter emails."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from imap_tools import MailBox, AND

from src.models import EmailItem

logger = logging.getLogger(__name__)


class GmailSource:
    """Fetch emails from Gmail via IMAP.

    Uses imap-tools for a clean API over raw imaplib.
    Requires an App Password (not regular password).
    """

    IMAP_HOST = "imap.gmail.com"

    def __init__(
        self,
        address: str,
        app_password: str,
        label: str = "Newsletters",
        lookback_hours: int = 24,
    ):
        self.address = address
        self.app_password = app_password
        self.label = label
        self.lookback_hours = lookback_hours

    def fetch(self) -> list[EmailItem]:
        """Fetch recent emails from the configured Gmail label."""
        since_date = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

        logger.info(
            f"Fetching emails from '{self.label}' since {since_date.isoformat()}"
        )

        emails: list[EmailItem] = []

        try:
            with MailBox(self.IMAP_HOST).login(
                self.address, self.app_password, initial_folder=self.label
            ) as mailbox:
                # Fetch emails from the last N hours
                criteria = AND(date_gte=since_date.date())

                for msg in mailbox.fetch(criteria, limit=50, reverse=True):
                    # Skip emails older than lookback window (date_gte is date-level)
                    if msg.date and msg.date < since_date:
                        continue

                    email_item = EmailItem(
                        id=msg.uid or str(hash(msg.subject)),
                        subject=msg.subject or "(No Subject)",
                        sender=msg.from_ or "Unknown",
                        date=msg.date or datetime.now(timezone.utc),
                        body_text=msg.text or "",
                        body_html=msg.html or "",
                        link="",  # Newsletters rarely have a canonical link in headers
                    )
                    emails.append(email_item)

        except Exception as e:
            logger.error(f"Failed to fetch emails from Gmail: {e}")
            raise

        logger.info(f"Fetched {len(emails)} emails from '{self.label}'")
        return emails
