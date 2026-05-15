"""Base scraper protocol and common utilities for Twitter data fetching."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from src.sources.twitter.models import TweetItem

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Raised when a scraper fails to fetch data."""

    pass


class BaseScraper(ABC):
    """Abstract base class for Twitter scrapers.

    Each scraper implements a different channel for fetching tweets.
    They share the same interface so the TwitterSource can fallback
    between them seamlessly.
    """

    name: str = "base"

    @abstractmethod
    async def fetch_by_topic(
        self,
        topic: str,
        since: datetime,
        limit: int = 20,
    ) -> list[TweetItem]:
        """Fetch tweets for a given topic/keyword.

        Args:
            topic: Search keyword or hashtag.
            since: Only fetch tweets after this datetime.
            limit: Maximum number of tweets to return.

        Returns:
            List of TweetItem sorted by engagement (descending).

        Raises:
            ScraperError: If the scraper fails.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this scraper is currently available/configured.

        Returns:
            True if the scraper can be used, False otherwise.
        """
        ...

    def _calculate_tweet_url(self, author_handle: str, tweet_id: str) -> str:
        """Build the canonical tweet URL."""
        return f"https://x.com/{author_handle}/status/{tweet_id}"
