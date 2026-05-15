"""Scraper channel 1: twscrape — open-source Twitter scraper.

twscrape uses Twitter's internal API with account pool authentication.
It's free, fast, and reliable as long as accounts are active.

Requires: pip install twscrape
Config: TWSCRAPE_ACCOUNTS env var with format "user:pass:email:emailpass,..."
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from src.sources.twitter.models import TweetItem
from src.sources.twitter.scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)


class TwscrapeScraper(BaseScraper):
    """Fetch tweets using twscrape library."""

    name = "twscrape"

    def __init__(self, accounts: list[dict] | None = None, debug: bool = False):
        """Initialize twscrape scraper.

        Args:
            accounts: List of account dicts with keys: username, password, email, email_password
            debug: Enable debug logging.
        """
        self.accounts = accounts or []
        self.debug = debug
        self._pool = None

    async def _get_pool(self):
        """Lazy-initialize the twscrape account pool."""
        if self._pool is not None:
            return self._pool

        try:
            from twscrape import AccountsPool, API

            self._pool = API()

            # Add accounts if not already added
            pool = AccountsPool()
            for acc in self.accounts:
                await pool.add_account(
                    acc["username"],
                    acc["password"],
                    acc["email"],
                    acc["email_password"],
                )
            await pool.login_all()
            self._pool = API(pool=pool)

            if self.debug:
                logger.debug(f"[twscrape] Pool initialized with {len(self.accounts)} accounts")

            return self._pool
        except ImportError:
            raise ScraperError("twscrape is not installed. Run: pip install twscrape")
        except Exception as e:
            raise ScraperError(f"Failed to initialize twscrape pool: {e}")

    async def fetch_by_topic(
        self,
        topic: str,
        since: datetime,
        limit: int = 20,
    ) -> list[TweetItem]:
        """Fetch tweets for a topic using twscrape search."""
        try:
            api = await self._get_pool()

            # Build search query — focus on popular tweets with engagement
            query = f"{topic} min_faves:10 -is:retweet lang:en OR lang:zh"
            since_str = since.strftime("%Y-%m-%d")
            query += f" since:{since_str}"

            if self.debug:
                logger.debug(f"[twscrape] Searching: {query}")

            tweets: list[TweetItem] = []
            count = 0

            async for tweet in api.search(query, limit=limit * 2):
                count += 1
                if count > limit * 2:
                    break

                # Filter by actual datetime (search is date-level only)
                tweet_date = tweet.date
                if tweet_date.tzinfo is None:
                    tweet_date = tweet_date.replace(tzinfo=timezone.utc)
                if tweet_date < since:
                    continue

                # Extract media URLs
                media_urls = []
                if hasattr(tweet, "media") and tweet.media:
                    for m in tweet.media.photos or []:
                        media_urls.append(m.url)

                item = TweetItem(
                    id=str(tweet.id),
                    author=tweet.user.displayname if tweet.user else "Unknown",
                    author_handle=tweet.user.username if tweet.user else "",
                    content=tweet.rawContent or "",
                    date=tweet_date,
                    likes=tweet.likeCount or 0,
                    retweets=tweet.retweetCount or 0,
                    replies=tweet.replyCount or 0,
                    views=tweet.viewCount or 0,
                    media_urls=media_urls,
                    topic=topic,
                    language=tweet.lang or "",
                )
                item.link = item.url
                tweets.append(item)

            # Sort by engagement score
            tweets.sort(key=lambda t: t.engagement_score, reverse=True)

            if self.debug:
                logger.debug(
                    f"[twscrape] Topic '{topic}': scanned {count} tweets, "
                    f"returning top {min(limit, len(tweets))}"
                )

            return tweets[:limit]

        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"twscrape fetch failed for topic '{topic}': {e}")

    async def is_available(self) -> bool:
        """Check if twscrape is installed and accounts are configured."""
        try:
            import twscrape  # noqa: F401
            return len(self.accounts) > 0
        except ImportError:
            return False
