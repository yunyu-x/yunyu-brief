"""Scraper channel 2: Nitter RSS — fetch tweets via Nitter instances.

Nitter is an open-source Twitter frontend that provides RSS feeds.
No authentication required, but public instances may be unreliable.

Features:
- Auto health-check: marks dead instances and skips them
- Auto discovery: fetches live instance lists from public sources
- Fallback chain: tries multiple instances until one works

Config: NITTER_INSTANCES env var with comma-separated URLs (optional).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from src.sources.twitter.models import TweetItem
from src.sources.twitter.scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

# Hardcoded seed instances (will be supplemented by auto-discovery)
SEED_NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.unixfox.eu",
    "https://nitter.mint.lgbt",
    "https://nitter.projectsegfau.lt",
]

# Known public sources that list active Nitter instances
INSTANCE_DISCOVERY_URLS = [
    # xnaas maintains a JSON list of Nitter instances
    "https://raw.githubusercontent.com/xnaas/nitter-instances/master/instances.json",
    # Alternative: wiki-based list (HTML, will be parsed differently)
    "https://raw.githubusercontent.com/zedeus/nitter/master/wiki/Instances.md",
]

# Health check cache file (persists between runs to remember dead instances)
HEALTH_CACHE_PATH = Path(__file__).parent.parent.parent.parent.parent / ".nitter_health_cache.json"
HEALTH_CACHE_TTL = 3600  # 1 hour — re-check dead instances after this time


class NitterHealthCache:
    """Tracks instance health status with TTL-based expiration.

    Persists to disk so that dead instances are remembered between runs.
    """

    def __init__(self, cache_path: Path = HEALTH_CACHE_PATH, ttl: int = HEALTH_CACHE_TTL):
        self.cache_path = cache_path
        self.ttl = ttl
        self._cache: dict[str, dict] = {}  # url -> {"alive": bool, "checked_at": float}
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        try:
            if self.cache_path.exists():
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._cache = data
        except (json.JSONDecodeError, OSError):
            self._cache = {}

    def _save(self) -> None:
        """Persist cache to disk."""
        try:
            self.cache_path.write_text(
                json.dumps(self._cache, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # Non-critical, will just re-check next time

    def is_known_dead(self, url: str) -> bool:
        """Check if an instance is known to be dead (within TTL)."""
        entry = self._cache.get(url)
        if entry is None:
            return False
        if entry.get("alive", True):
            return False
        # Check if TTL expired (time to re-check)
        checked_at = entry.get("checked_at", 0)
        if time.time() - checked_at > self.ttl:
            return False  # TTL expired, allow re-check
        return True

    def mark_alive(self, url: str) -> None:
        """Mark an instance as alive."""
        self._cache[url] = {"alive": True, "checked_at": time.time()}
        self._save()

    def mark_dead(self, url: str) -> None:
        """Mark an instance as dead."""
        self._cache[url] = {"alive": False, "checked_at": time.time()}
        self._save()

    def get_alive_instances(self) -> list[str]:
        """Return instances known to be alive."""
        now = time.time()
        alive = []
        for url, entry in self._cache.items():
            if entry.get("alive") and (now - entry.get("checked_at", 0)) < self.ttl * 24:
                alive.append(url)
        return alive


class NitterScraper(BaseScraper):
    """Fetch tweets using Nitter RSS feeds with auto-discovery and health management."""

    name = "nitter"

    def __init__(
        self,
        instances: list[str] | None = None,
        debug: bool = False,
        auto_discover: bool = True,
    ):
        """Initialize Nitter scraper.

        Args:
            instances: User-configured Nitter instance URLs.
            debug: Enable debug logging.
            auto_discover: If True, automatically discover live instances.
        """
        self._user_instances = instances or []
        self._auto_discover = auto_discover
        self.debug = debug
        self._health_cache = NitterHealthCache()
        self._discovered_instances: list[str] | None = None

    @property
    def instances(self) -> list[str]:
        """Get the prioritized list of instances to try.

        Priority:
        1. User-configured instances (from .env)
        2. Previously known-alive instances (from health cache)
        3. Auto-discovered instances
        4. Hardcoded seed instances
        """
        all_instances: list[str] = []
        seen: set[str] = set()

        def _add(urls: list[str]):
            for url in urls:
                url = url.rstrip("/")
                if url not in seen:
                    seen.add(url)
                    all_instances.append(url)

        # Priority 1: User configured
        _add(self._user_instances)

        # Priority 2: Known alive from cache
        _add(self._health_cache.get_alive_instances())

        # Priority 3: Auto-discovered (if already fetched)
        if self._discovered_instances:
            _add(self._discovered_instances)

        # Priority 4: Seed instances
        _add(SEED_NITTER_INSTANCES)

        # Filter out known-dead instances (but keep them at the end as last resort)
        alive_or_unknown = [u for u in all_instances if not self._health_cache.is_known_dead(u)]
        known_dead = [u for u in all_instances if self._health_cache.is_known_dead(u)]

        return alive_or_unknown + known_dead

    async def _discover_instances(self) -> list[str]:
        """Auto-discover active Nitter instances from public sources."""
        if self._discovered_instances is not None:
            return self._discovered_instances

        discovered: list[str] = []

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                for url in INSTANCE_DISCOVERY_URLS:
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            continue

                        if url.endswith(".json"):
                            # JSON format: list of instance objects
                            data = resp.json()
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, str):
                                        discovered.append(item.rstrip("/"))
                                    elif isinstance(item, dict):
                                        inst_url = item.get("url") or item.get("instance") or ""
                                        if inst_url and inst_url.startswith("http"):
                                            discovered.append(inst_url.rstrip("/"))
                        elif url.endswith(".md"):
                            # Markdown format: extract URLs
                            import re
                            urls_found = re.findall(
                                r"https?://[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}(?:/[^\s)]*)?",
                                resp.text,
                            )
                            for u in urls_found:
                                u = u.rstrip("/").rstrip(")")
                                if "nitter" in u.lower() or any(
                                    kw in u for kw in [".net", ".org", ".cafe", ".us"]
                                ):
                                    discovered.append(u)

                        if self.debug:
                            logger.debug(
                                f"[nitter] Discovered {len(discovered)} instances from {url}"
                            )
                        break  # One successful source is enough

                    except Exception as e:
                        if self.debug:
                            logger.debug(f"[nitter] Discovery from {url} failed: {e}")
                        continue

        except ImportError:
            pass

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for inst in discovered:
            if inst not in seen and inst.startswith("https://"):
                seen.add(inst)
                unique.append(inst)

        self._discovered_instances = unique
        if self.debug and unique:
            logger.debug(f"[nitter] Total discovered instances: {len(unique)}")

        return unique

    async def fetch_by_topic(
        self,
        topic: str,
        since: datetime,
        limit: int = 20,
    ) -> list[TweetItem]:
        """Fetch tweets for a topic using Nitter search RSS.

        Automatically tries multiple instances, marks dead ones, and
        discovers new ones if needed.
        """
        import httpx
        import xml.etree.ElementTree as ET

        # Auto-discover instances if enabled
        if self._auto_discover:
            await self._discover_instances()

        instances_to_try = self.instances
        errors = []
        tried_count = 0
        max_tries = min(len(instances_to_try), 8)  # Don't try more than 8

        for instance in instances_to_try[:max_tries]:
            tried_count += 1
            try:
                encoded_topic = quote_plus(topic)
                url = f"{instance}/search/rss?f=tweets&q={encoded_topic}"

                if self.debug:
                    logger.debug(
                        f"[nitter] Trying ({tried_count}/{max_tries}): {url}"
                    )

                async with httpx.AsyncClient(
                    timeout=12.0,
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
                        logger.debug(f"[nitter] No channel in RSS from {instance}")
                    # Not necessarily dead — might just have no results
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

                # Mark this instance as alive
                self._health_cache.mark_alive(instance)

                # Sort by engagement
                tweets.sort(key=lambda t: t.engagement_score, reverse=True)

                if self.debug:
                    logger.debug(
                        f"[nitter] Topic '{topic}' via {instance}: "
                        f"found {len(tweets)} tweets"
                    )

                if tweets:
                    return tweets[:limit]
                # If no tweets found but instance is alive, try next
                # (might just have no results for this topic)
                continue

            except Exception as e:
                # Mark instance as dead
                self._health_cache.mark_dead(instance)
                errors.append(f"{instance}: {e}")
                if self.debug:
                    logger.debug(
                        f"[nitter] Instance {instance} DEAD, marked for skip: {e}"
                    )
                continue

        raise ScraperError(
            f"All {tried_count} Nitter instances failed for topic '{topic}': "
            + "; ".join(errors[-3:])  # Only show last 3 errors
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
        """Check if at least one Nitter instance is reachable.

        Tries known-alive instances first, then does auto-discovery.
        """
        try:
            import httpx

            # First check cached alive instances
            alive = self._health_cache.get_alive_instances()
            instances_to_check = alive[:2] if alive else SEED_NITTER_INSTANCES[:3]

            for instance in instances_to_check:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(f"{instance}/")
                        if resp.status_code < 500:
                            self._health_cache.mark_alive(instance)
                            return True
                        else:
                            self._health_cache.mark_dead(instance)
                except Exception:
                    self._health_cache.mark_dead(instance)
                    continue

            # If none of the quick checks passed, try auto-discovery
            if self._auto_discover:
                discovered = await self._discover_instances()
                for instance in discovered[:3]:
                    try:
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            resp = await client.get(f"{instance}/")
                            if resp.status_code < 500:
                                self._health_cache.mark_alive(instance)
                                return True
                    except Exception:
                        self._health_cache.mark_dead(instance)
                        continue

            return False
        except ImportError:
            return False
