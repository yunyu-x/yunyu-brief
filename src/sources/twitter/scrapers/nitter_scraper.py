"""Scraper channel 2: Nitter RSS — fetch tweets via Nitter instances.

Nitter is an open-source Twitter frontend that provides RSS feeds.
No authentication required, but public instances may be unreliable.

Config: NITTER_INSTANCES env var with comma-separated URLs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

from src.sources.twitter.models import TweetItem
from src.sources.twitter.scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

# Default Nitter instances (public, may change over time)
DEFAULT_NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
]


class NitterScraper(BaseScraper):
    """Fetch tweets using Nitter RSS feeds."""

    name = "nitter"

    def __init__(
        self,
        instances: list[str] | None = None,
        debug: bool = False,
    ):
        """Initialize Nitter scraper.

        Args:
            instances: List of Nitter instance URLs to try.
            debug: Enable debug logging.
        """
        self.instances = instances or DEFAULT_NITTER_INSTANCES
        self.debug = debug

    async def fetch_by_topic(
        self,
        topic: str,
        since: datetime,
        limit: int = 20,
    ) -> list[TweetItem]:
        """Fetch tweets for a topic using Nitter search RSS."""
        import httpx
        import xml.etree.ElementTree as ET
        from email.utils import parsedate_to_datetime
        import re

        errors = []

        for instance in self.instances:
            try:
                # Nitter search RSS endpoint
                encoded_topic = quote_plus(topic)
                url = f"{instance}/search/rss?f=tweets&q={encoded_topic}"

                if self.debug:
                    logger.debug(f"[nitter] Trying: {url}")

                async with httpx.AsyncClient(
                    timeout=15.0,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Paperboy/1.0)"},
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                # Parse RSS XML
                root = ET.fromstring(response.text)
                channel = root.find("channel")
                if channel is None:
                    if self.debug:
                        logger.debug(f"[nitter] No channel found in RSS from {instance}")
                    continue

                tweets: list[TweetItem] = []

                for item in channel.findall("item"):
                    try:
                        tweet = self._parse_rss_item(item, topic, since)
                        if tweet:
                            tweets.append(tweet)
                    except Exception as e:
                        if self.debug:
                            logger.debug(f"[nitter] Failed to parse item: {e}")
                        continue

                # Sort by engagement (Nitter RSS has limited engagement data)
                tweets.sort(key=lambda t: t.engagement_score, reverse=True)

                if self.debug:
                    logger.debug(
                        f"[nitter] Topic '{topic}' via {instance}: "
                        f"found {len(tweets)} tweets"
                    )

                return tweets[:limit]

            except Exception as e:
                errors.append(f"{instance}: {e}")
                if self.debug:
                    logger.debug(f"[nitter] Instance {instance} failed: {e}")
                continue

        raise ScraperError(
            f"All Nitter instances failed for topic '{topic}': "
            + "; ".join(errors)
        )

    def _parse_rss_item(
        self,
        item,
        topic: str,
        since: datetime,
    ) -> TweetItem | None:
        """Parse a single RSS item into a TweetItem."""
        from email.utils import parsedate_to_datetime
        import re

        title = item.findtext("title", "")
        description = item.findtext("description", "")
        link = item.findtext("link", "")
        pub_date_str = item.findtext("pubDate", "")
        creator = item.findtext("{http://purl.org/dc/elements/1.1/}creator", "")

        if not title and not description:
            return None

        # Parse date
        try:
            pub_date = parsedate_to_datetime(pub_date_str)
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pub_date = datetime.now(timezone.utc)

        # Filter by time
        if pub_date < since:
            return None

        # Extract author handle from creator or link
        author_handle = ""
        if creator:
            author_handle = creator.lstrip("@")
        elif link:
            # Link format: https://nitter.xxx/@user/status/12345
            match = re.search(r"/@?(\w+)/status/(\d+)", link)
            if match:
                author_handle = match.group(1)

        # Extract tweet ID from link
        tweet_id = ""
        if link:
            match = re.search(r"/status/(\d+)", link)
            if match:
                tweet_id = match.group(1)

        # Clean content — strip HTML tags from description
        content = re.sub(r"<[^>]+>", "", description) if description else title

        # Extract media URLs from description HTML
        media_urls = []
        if description:
            img_matches = re.findall(r'<img[^>]+src="([^"]+)"', description)
            media_urls = [url for url in img_matches if "pic" in url or "media" in url]

        # Convert Nitter link to real Twitter link
        real_link = ""
        if author_handle and tweet_id:
            real_link = f"https://x.com/{author_handle}/status/{tweet_id}"

        return TweetItem(
            id=tweet_id or str(hash(title)),
            author=creator or author_handle or "Unknown",
            author_handle=author_handle,
            content=content,
            date=pub_date,
            likes=0,  # Nitter RSS doesn't provide engagement stats
            retweets=0,
            replies=0,
            views=0,
            media_urls=media_urls,
            link=real_link,
            topic=topic,
        )

    async def is_available(self) -> bool:
        """Check if at least one Nitter instance is reachable."""
        try:
            import httpx

            for instance in self.instances[:2]:  # Only check first 2
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(f"{instance}/")
                        if resp.status_code < 500:
                            return True
                except Exception:
                    continue
            return False
        except ImportError:
            return False
