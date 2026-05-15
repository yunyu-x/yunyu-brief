"""Scraper channel 3: Official X API v2 (Free Tier).

Uses Twitter's official API v2 with Bearer Token.
Free tier limits: 10,000 tweets read/month, basic search only.

Config: TWITTER_BEARER_TOKEN env var.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.sources.twitter.models import TweetItem
from src.sources.twitter.scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)


class OfficialAPIScraper(BaseScraper):
    """Fetch tweets using the official X/Twitter API v2."""

    name = "official_api"
    BASE_URL = "https://api.twitter.com/2"

    def __init__(self, bearer_token: str = "", debug: bool = False):
        """Initialize official API scraper.

        Args:
            bearer_token: X API Bearer Token.
            debug: Enable debug logging.
        """
        self.bearer_token = bearer_token
        self.debug = debug

    async def fetch_by_topic(
        self,
        topic: str,
        since: datetime,
        limit: int = 20,
    ) -> list[TweetItem]:
        """Fetch tweets using Twitter API v2 recent search."""
        import httpx

        if not self.bearer_token:
            raise ScraperError("Twitter Bearer Token not configured")

        try:
            headers = {
                "Authorization": f"Bearer {self.bearer_token}",
                "Content-Type": "application/json",
            }

            # Build query — exclude retweets, require some engagement
            query = f"{topic} -is:retweet has:media OR has:links"
            since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

            params = {
                "query": query,
                "start_time": since_str,
                "max_results": min(limit, 100),  # API max is 100
                "sort_order": "relevancy",
                "tweet.fields": "created_at,public_metrics,author_id,lang,attachments",
                "expansions": "author_id,attachments.media_keys",
                "user.fields": "name,username",
                "media.fields": "url,preview_image_url,type",
            }

            if self.debug:
                logger.debug(f"[official_api] Query: {query}")
                logger.debug(f"[official_api] Since: {since_str}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/tweets/search/recent",
                    headers=headers,
                    params=params,
                )

                if response.status_code == 429:
                    raise ScraperError("Twitter API rate limit exceeded")
                response.raise_for_status()

            data = response.json()

            if "data" not in data:
                if self.debug:
                    logger.debug(f"[official_api] No data in response: {data}")
                return []

            # Build user lookup map
            users_map: dict[str, dict] = {}
            if "includes" in data and "users" in data["includes"]:
                for user in data["includes"]["users"]:
                    users_map[user["id"]] = user

            # Build media lookup map
            media_map: dict[str, str] = {}
            if "includes" in data and "media" in data["includes"]:
                for media in data["includes"]["media"]:
                    url = media.get("url") or media.get("preview_image_url", "")
                    if url:
                        media_map[media["media_key"]] = url

            tweets: list[TweetItem] = []

            for tweet_data in data["data"]:
                tweet = self._parse_tweet(tweet_data, users_map, media_map, topic)
                if tweet and tweet.date >= since:
                    tweets.append(tweet)

            # Sort by engagement
            tweets.sort(key=lambda t: t.engagement_score, reverse=True)

            if self.debug:
                logger.debug(
                    f"[official_api] Topic '{topic}': "
                    f"found {len(tweets)} tweets from API"
                )

            return tweets[:limit]

        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"Official API failed for topic '{topic}': {e}")

    def _parse_tweet(
        self,
        tweet_data: dict,
        users_map: dict[str, dict],
        media_map: dict[str, str],
        topic: str,
    ) -> TweetItem | None:
        """Parse API response into TweetItem."""
        try:
            tweet_id = tweet_data["id"]
            text = tweet_data.get("text", "")
            metrics = tweet_data.get("public_metrics", {})
            author_id = tweet_data.get("author_id", "")
            lang = tweet_data.get("lang", "")

            # Parse date
            created_at = tweet_data.get("created_at", "")
            try:
                date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                date = datetime.now(timezone.utc)

            # Get author info
            user = users_map.get(author_id, {})
            author_name = user.get("name", "Unknown")
            author_handle = user.get("username", "")

            # Get media URLs
            media_urls = []
            attachments = tweet_data.get("attachments", {})
            media_keys = attachments.get("media_keys", [])
            for key in media_keys:
                if key in media_map:
                    media_urls.append(media_map[key])

            link = f"https://x.com/{author_handle}/status/{tweet_id}" if author_handle else ""

            return TweetItem(
                id=tweet_id,
                author=author_name,
                author_handle=author_handle,
                content=text,
                date=date,
                likes=metrics.get("like_count", 0),
                retweets=metrics.get("retweet_count", 0),
                replies=metrics.get("reply_count", 0),
                views=metrics.get("impression_count", 0),
                media_urls=media_urls,
                link=link,
                topic=topic,
                language=lang,
            )
        except Exception as e:
            if self.debug:
                logger.debug(f"[official_api] Failed to parse tweet: {e}")
            return None

    async def is_available(self) -> bool:
        """Check if Bearer Token is configured."""
        return bool(self.bearer_token)
