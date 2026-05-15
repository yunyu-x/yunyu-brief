"""TwitterSource — main class that orchestrates multi-channel fetching with fallback.

This is the primary interface for fetching trending tech tweets.
It manages multiple scraper channels and falls back between them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.sources.twitter.models import TweetItem
from src.sources.twitter.scrapers.base import BaseScraper, ScraperError
from src.sources.twitter.scrapers.twikit_scraper import TwikitScraper
from src.sources.twitter.scrapers.twscrape_scraper import TwscrapeScraper
from src.sources.twitter.scrapers.nitter_scraper import NitterScraper
from src.sources.twitter.scrapers.official_api import OfficialAPIScraper

logger = logging.getLogger(__name__)

# Default broad tech topics when user doesn't configure specific ones
DEFAULT_TOPICS = [
    "AI Agent",
    "LLM",
    "machine learning",
    "Python",
    "software engineering",
]


class TwitterSource:
    """Fetch trending tech tweets from X/Twitter with multi-channel fallback.

    Fetching priority (updated 2025 — Nitter public instances are mostly dead):
      1. Official X API (most reliable, free tier: 10k tweets/month)
      2. twscrape (full data, needs accounts)
      3. Nitter RSS (last resort, most instances are dead)

    For each topic, we fetch top N tweets by engagement, then return the
    combined and de-duplicated set sorted by engagement score.
    """

    def __init__(
        self,
        topics: list[str] | None = None,
        lookback_hours: int = 24,
        top_per_topic: int = 20,
        final_top: int = 10,
        twikit_username: str = "",
        twikit_email: str = "",
        twikit_password: str = "",
        twikit_cookies_path: str = "",
        twscrape_accounts: list[dict] | None = None,
        nitter_instances: list[str] | None = None,
        bearer_token: str = "",
        debug: bool = False,
    ):
        """Initialize TwitterSource.

        Args:
            topics: List of tech topics to search (max 10). Uses defaults if empty.
            lookback_hours: How far back to look for tweets.
            top_per_topic: How many top tweets to fetch per topic.
            final_top: How many tweets to include in final output (for Agent).
            twikit_username: X username for twikit login.
            twikit_email: Email for twikit login.
            twikit_password: Password for twikit login.
            twikit_cookies_path: Path to twikit cookies file.
            twscrape_accounts: Account dicts for twscrape.
            nitter_instances: Nitter instance URLs.
            bearer_token: X API Bearer Token.
            debug: Enable debug logging.
        """
        self.topics = (topics or DEFAULT_TOPICS)[:10]  # Max 10 topics
        self.lookback_hours = lookback_hours
        self.top_per_topic = top_per_topic
        self.final_top = final_top
        self.debug = debug

        # Initialize scrapers in priority order:
        # 1. twikit (free, cookie-based, best data)
        # 2. Official API (paid per-use since 2026)
        # 3. twscrape (needs account pool)
        # 4. Nitter (last resort, mostly dead)
        self._scrapers: list[BaseScraper] = [
            TwikitScraper(
                username=twikit_username,
                email=twikit_email,
                password=twikit_password,
                cookies_path=twikit_cookies_path,
                debug=debug,
            ),
            OfficialAPIScraper(bearer_token=bearer_token, debug=debug),
            TwscrapeScraper(accounts=twscrape_accounts or [], debug=debug),
            NitterScraper(instances=nitter_instances, debug=debug),
        ]

    def fetch(self) -> list[TweetItem]:
        """Fetch trending tech tweets (sync wrapper for async internals).

        Returns:
            List of TweetItem sorted by engagement, de-duplicated across topics.
        """
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[TweetItem]:
        """Async implementation of the fetch pipeline."""
        since = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

        logger.info(
            f"Fetching tweets for {len(self.topics)} topics, "
            f"lookback={self.lookback_hours}h, top_per_topic={self.top_per_topic}"
        )
        if self.debug:
            logger.debug(f"[twitter] Topics: {self.topics}")
            logger.debug(f"[twitter] Since: {since.isoformat()}")
            logger.debug(f"[twitter] Scrapers: {[s.name for s in self._scrapers]}")

        # Determine which scrapers are available
        available_scrapers = await self._get_available_scrapers()

        if not available_scrapers:
            logger.error("No Twitter scrapers available. Check your configuration.")
            return []

        if self.debug:
            logger.debug(
                f"[twitter] Available scrapers: {[s.name for s in available_scrapers]}"
            )

        # Fetch tweets for all topics
        all_tweets: list[TweetItem] = []

        for topic in self.topics:
            topic_tweets = await self._fetch_topic_with_fallback(
                topic, since, available_scrapers
            )
            all_tweets.extend(topic_tweets)

            if self.debug:
                logger.debug(
                    f"[twitter] Topic '{topic}': got {len(topic_tweets)} tweets"
                )

        # De-duplicate by tweet ID
        seen_ids: set[str] = set()
        unique_tweets: list[TweetItem] = []
        for tweet in all_tweets:
            if tweet.id not in seen_ids:
                seen_ids.add(tweet.id)
                unique_tweets.append(tweet)

        # Sort all tweets by engagement score
        unique_tweets.sort(key=lambda t: t.engagement_score, reverse=True)

        total_fetched = len(unique_tweets)
        result = unique_tweets[: self.top_per_topic * len(self.topics)]

        logger.info(
            f"Twitter fetch complete: {total_fetched} unique tweets, "
            f"returning top {len(result)} for Agent processing"
        )

        if self.debug:
            logger.debug("[twitter] Top 5 tweets by engagement:")
            for i, t in enumerate(result[:5], 1):
                logger.debug(
                    f"[twitter]   {i}. [{t.topic}] @{t.author_handle}: "
                    f"'{t.content[:60]}...' "
                    f"(score={t.engagement_score:.0f}, "
                    f"likes={t.likes}, rt={t.retweets})"
                )

        return result

    async def _get_available_scrapers(self) -> list[BaseScraper]:
        """Check which scrapers are currently available."""
        available = []
        for scraper in self._scrapers:
            try:
                if await scraper.is_available():
                    available.append(scraper)
                elif self.debug:
                    logger.debug(f"[twitter] Scraper '{scraper.name}' not available")
            except Exception as e:
                if self.debug:
                    logger.debug(
                        f"[twitter] Scraper '{scraper.name}' check failed: {e}"
                    )
        return available

    async def _fetch_topic_with_fallback(
        self,
        topic: str,
        since: datetime,
        scrapers: list[BaseScraper],
    ) -> list[TweetItem]:
        """Fetch tweets for a single topic, trying scrapers in priority order.

        If a scraper fails, fall back to the next one.
        """
        for scraper in scrapers:
            try:
                if self.debug:
                    logger.debug(
                        f"[twitter] Trying '{scraper.name}' for topic '{topic}'"
                    )

                tweets = await scraper.fetch_by_topic(
                    topic=topic,
                    since=since,
                    limit=self.top_per_topic,
                )

                if tweets:
                    logger.info(
                        f"Topic '{topic}' via {scraper.name}: {len(tweets)} tweets"
                    )
                    return tweets
                else:
                    if self.debug:
                        logger.debug(
                            f"[twitter] '{scraper.name}' returned 0 tweets for '{topic}', "
                            f"trying next scraper"
                        )
                    continue

            except ScraperError as e:
                logger.warning(
                    f"Scraper '{scraper.name}' failed for topic '{topic}': {e}"
                )
                continue
            except Exception as e:
                logger.warning(
                    f"Unexpected error from '{scraper.name}' for topic '{topic}': {e}"
                )
                continue

        logger.warning(f"All scrapers failed for topic '{topic}'")
        return []

    def get_topics(self) -> list[str]:
        """Return the configured topics."""
        return self.topics

    def get_scraper_status(self) -> dict[str, bool]:
        """Return availability status of each scraper (sync wrapper)."""
        return asyncio.run(self._get_scraper_status_async())

    async def _get_scraper_status_async(self) -> dict[str, bool]:
        """Check availability of each scraper."""
        status = {}
        for scraper in self._scrapers:
            try:
                status[scraper.name] = await scraper.is_available()
            except Exception:
                status[scraper.name] = False
        return status
