"""Data models for Twitter/X source."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TweetItem(BaseModel):
    """A single tweet fetched from X/Twitter."""

    id: str
    author: str
    author_handle: str = ""
    content: str
    date: datetime
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0
    media_urls: list[str] = Field(default_factory=list)
    link: str = ""
    topic: str = ""  # Which topic this tweet was found under
    language: str = ""

    @property
    def engagement_score(self) -> float:
        """Calculate comprehensive engagement score.

        Weights: likes(1x) + retweets(3x) + replies(2x) + views(0.01x)
        Retweets are weighted higher as they indicate content sharing value.
        """
        return (
            self.likes * 1.0
            + self.retweets * 3.0
            + self.replies * 2.0
            + self.views * 0.01
        )

    @property
    def preview(self) -> str:
        """Return a truncated preview of the content."""
        text = self.content or ""
        if len(text) > 280:
            return text[:280] + "..."
        return text

    @property
    def url(self) -> str:
        """Return the tweet URL."""
        if self.link:
            return self.link
        if self.author_handle and self.id:
            return f"https://x.com/{self.author_handle}/status/{self.id}"
        return ""


class TwitterBriefingItem(BaseModel):
    """A single item in the Twitter tech briefing."""

    title: str
    author: str
    author_handle: str = ""
    summary: str
    link: str
    topic: str = ""
    engagement: str = ""  # Human-readable engagement stats
    media_urls: list[str] = Field(default_factory=list)


class TwitterBriefing(BaseModel):
    """The structured Twitter tech briefing output."""

    date: str
    total_fetched: int = 0
    topics: list[str] = Field(default_factory=list)
    top10: list[TwitterBriefingItem] = Field(default_factory=list)
    trends_summary: str = ""  # Agent's overall analysis of tech trends
    keywords: list[str] = Field(default_factory=list)
