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
        label: str = "",
        lookback_hours: int = 24,
        debug: bool = False,
    ):
        self.address = address
        self.app_password = app_password
        # Empty string or not set → use INBOX (all emails)
        self.label = label if label else "INBOX"
        self.lookback_hours = lookback_hours
        self.debug = debug

    def fetch(self) -> list[EmailItem]:
        """Fetch recent emails from the configured Gmail label."""
        since_date = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

        logger.info(
            f"Fetching emails from '{self.label}' since {since_date.isoformat()}"
        )

        if self.debug:
            logger.debug(f"[IMAP] Host: {self.IMAP_HOST}:993 (SSL)")
            logger.debug(f"[IMAP] Account: {self.address[:3]}***@{self.address.split('@')[-1]}")
            logger.debug(f"[IMAP] Folder/Label: {self.label}")
            logger.debug(f"[IMAP] Since: {since_date.isoformat()}")
            logger.debug(f"[IMAP] Lookback: {self.lookback_hours} hours")

        emails: list[EmailItem] = []

        try:
            if self.debug:
                logger.debug("[IMAP] Connecting to imap.gmail.com...")

            with MailBox(self.IMAP_HOST).login(
                self.address, self.app_password, initial_folder=self.label
            ) as mailbox:
                if self.debug:
                    logger.debug(f"[IMAP] ✅ Login successful, folder '{self.label}' selected")

                # Fetch emails from the last N hours
                criteria = AND(date_gte=since_date.date())

                if self.debug:
                    logger.debug(f"[IMAP] Search criteria: date >= {since_date.date()}")
                    logger.debug("[IMAP] Fetching messages (limit=50, reverse=True)...")

                msg_count = 0
                skipped_count = 0

                for msg in mailbox.fetch(criteria, limit=50, reverse=True):
                    msg_count += 1

                    # Skip emails older than lookback window (date_gte is date-level)
                    if msg.date and msg.date < since_date:
                        skipped_count += 1
                        if self.debug:
                            logger.debug(
                                f"[IMAP]   SKIP #{msg_count}: '{msg.subject}' "
                                f"(date {msg.date} < {since_date})"
                            )
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

                    if self.debug:
                        logger.debug(
                            f"[IMAP]   ✓ #{msg_count} UID={email_item.id} "
                            f"Subject='{email_item.subject[:50]}' "
                            f"From='{email_item.sender}' "
                            f"Date={email_item.date} "
                            f"BodyLen={len(email_item.body_text)} chars"
                        )

                if self.debug:
                    logger.debug(
                        f"[IMAP] Scan complete: {msg_count} messages scanned, "
                        f"{len(emails)} matched, {skipped_count} skipped (too old)"
                    )

        except Exception as e:
            logger.error(f"Failed to fetch emails from Gmail: {e}")
            if self.debug:
                logger.debug(f"[IMAP] ❌ Exception type: {type(e).__name__}")
                logger.debug(f"[IMAP] ❌ Exception detail: {e}")
                import traceback
                logger.debug(f"[IMAP] ❌ Traceback:\n{traceback.format_exc()}")
            raise

        logger.info(f"Fetched {len(emails)} emails from '{self.label}'")
        return emails
