"""Scraper channel: twikit — cookie-based Twitter scraper (no API key needed).

twikit uses Twitter's internal GraphQL API with cookie authentication.
It's free, actively maintained (2026), and provides full tweet data including
engagement metrics.

Requires: pip install twikit
Config: TWIKIT_USERNAME, TWIKIT_EMAIL, TWIKIT_PASSWORD, or a cookies file.

Usage:
    First run: logs in with credentials, saves cookies to disk.
    Subsequent runs: loads cookies from disk (no login needed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.sources.twitter.models import TweetItem
from src.sources.twitter.scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

# Default cookies file path
DEFAULT_COOKIES_PATH = Path(".twikit_cookies.json")


class TwikitScraper(BaseScraper):
    """Fetch tweets using twikit library (cookie-based, no API key)."""

    name = "twikit"

    def __init__(
        self,
        username: str = "",
        email: str = "",
        password: str = "",
        cookies_path: str = "",
        debug: bool = False,
    ):
        """Initialize twikit scraper.

        Args:
            username: X/Twitter username (for first-time login).
            email: Email associated with the X account.
            password: Account password.
            cookies_path: Path to save/load cookies file.
            debug: Enable debug logging.
        """
        self.username = username
        self.email = email
        self.password = password
        self.cookies_path = Path(cookies_path) if cookies_path else DEFAULT_COOKIES_PATH
        self.debug = debug
        self._client = None

    async def _get_client(self):
        """Lazy-initialize and authenticate the twikit client."""
        if self._client is not None:
            return self._client

        try:
            from twikit import Client
        except ImportError:
            raise ScraperError(
                "twikit is not installed. Run: pip install twikit"
            )

        try:
            client = Client("en-US")

            # Try loading existing cookies first
            if self.cookies_path.exists():
                if self.debug:
                    logger.debug(f"[twikit] Loading cookies from {self.cookies_path}")
                client.load_cookies(str(self.cookies_path))
                self._client = client
                return self._client

            # No cookies — need to login with credentials
            if not self.username or not self.password:
                raise ScraperError(
                    "twikit requires either a cookies file or credentials "
                    "(TWIKIT_USERNAME + TWIKIT_PASSWORD + TWIKIT_EMAIL). "
                    "Please configure them in your .env file."
                )

            if self.debug:
                logger.debug(f"[twikit] Logging in as {self.username}...")

            await client.login(
                auth_info_1=self.username,
                auth_info_2=self.email,
                password=self.password,
            )

            # Save cookies for future use
            client.save_cookies(str(self.cookies_path))
            if self.debug:
                logger.debug(f"[twikit] Cookies saved to {self.cookies_path}")

            self._client = client
            return self._client

        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"Failed to initialize twikit client: {e}")

    async def fetch_by_topic(
        self,
        topic: str,
        since: datetime,
        limit: int = 20,
    ) -> list[TweetItem]:
        """Fetch tweets for a topic using twikit search."""
        try:
            client = await self._get_client()

            # twikit search_tweet: query, product ('Top', 'Latest', 'People', 'Media')
            # 'Top' gives us popular/engaging tweets
            if self.debug:
                logger.debug(f"[twikit] Searching: '{topic}' (product=Top, limit={limit})")

            result = await client.search_tweet(topic, product="Top", count=limit)

            tweets: list[TweetItem] = []

            for tweet in result:
                try:
                    parsed = self._parse_tweet(tweet, topic, since)
                    if parsed:
                        tweets.append(parsed)
                except Exception as e:
                    if self.debug:
                        logger.debug(f"[twikit] Failed to parse tweet: {e}")
                    continue

            # Sort by engagement score
            tweets.sort(key=lambda t: t.engagement_score, reverse=True)

            if self.debug:
                logger.debug(
                    f"[twikit] Topic '{topic}': found {len(tweets)} tweets"
                )

            return tweets[:limit]

        except ScraperError:
            raise
        except Exception as e:
            # If cookies expired, try to re-login
            if "401" in str(e) or "403" in str(e) or "unauthorized" in str(e).lower():
                logger.warning(f"[twikit] Auth error, cookies may be expired: {e}")
                # Delete stale cookies and retry login next time
                if self.cookies_path.exists():
                    self.cookies_path.unlink()
                    self._client = None
                raise ScraperError(
                    f"twikit auth expired for topic '{topic}'. "
                    f"Cookies deleted, will re-login next run. Error: {e}"
                )
            raise ScraperError(f"twikit fetch failed for topic '{topic}': {e}")

    def _parse_tweet(
        self,
        tweet,
        topic: str,
        since: datetime,
    ) -> TweetItem | None:
        """Parse a twikit Tweet object into our TweetItem model."""
        try:
            # Get tweet creation date
            created_at = tweet.created_at
            if isinstance(created_at, str):
                # twikit returns date as string like "Thu May 15 01:00:00 +0000 2026"
                from email.utils import parsedate_to_datetime
                try:
                    tweet_date = parsedate_to_datetime(created_at)
                except (ValueError, TypeError):
                    tweet_date = datetime.now(timezone.utc)
            elif isinstance(created_at, datetime):
                tweet_date = created_at
            else:
                tweet_date = datetime.now(timezone.utc)

            if tweet_date.tzinfo is None:
                tweet_date = tweet_date.replace(tzinfo=timezone.utc)

            # Filter by time window
            if tweet_date < since:
                return None

            # Extract user info
            user = tweet.user
            author_name = user.name if user else "Unknown"
            author_handle = user.screen_name if user else ""

            # Extract media URLs
            media_urls = []
            if hasattr(tweet, "media") and tweet.media:
                for media in tweet.media:
                    if hasattr(media, "media_url_https"):
                        media_urls.append(media.media_url_https)
                    elif hasattr(media, "url"):
                        media_urls.append(media.url)

            # Build tweet URL
            tweet_id = str(tweet.id)
            link = f"https://x.com/{author_handle}/status/{tweet_id}" if author_handle else ""

            # Get engagement metrics
            likes = getattr(tweet, "favorite_count", 0) or 0
            retweets = getattr(tweet, "retweet_count", 0) or 0
            replies = getattr(tweet, "reply_count", 0) or 0
            views = getattr(tweet, "view_count", 0) or 0

            # Get full text
            text = getattr(tweet, "full_text", "") or getattr(tweet, "text", "") or ""

            return TweetItem(
                id=tweet_id,
                author=author_name,
                author_handle=author_handle,
                content=text,
                date=tweet_date,
                likes=likes,
                retweets=retweets,
                replies=replies,
                views=views,
                media_urls=media_urls,
                link=link,
                topic=topic,
                language=getattr(tweet, "lang", "") or "",
            )
        except Exception as e:
            if self.debug:
                logger.debug(f"[twikit] Parse error: {e}")
            return None

    async def is_available(self) -> bool:
        """Check if twikit is installed and credentials/cookies are available."""
        try:
            import twikit  # noqa: F401
            # Available if we have cookies OR credentials
            has_cookies = self.cookies_path.exists()
            has_credentials = bool(self.username and self.password)
            return has_cookies or has_credentials
        except ImportError:
            return False
