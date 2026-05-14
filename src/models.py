"""Data models for Paperboy."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EmailItem(BaseModel):
    """A single email fetched from a source."""

    id: str
    subject: str
    sender: str
    date: datetime
    body_text: str = ""
    body_html: str = ""
    link: str = ""

    @property
    def preview(self) -> str:
        """Return a truncated preview of the body text."""
        text = self.body_text or ""
        if len(text) > 500:
            return text[:500] + "..."
        return text


class BriefingItem(BaseModel):
    """A single item in the daily briefing."""

    title: str
    source: str
    summary: str
    link: str = ""


class DailyBriefing(BaseModel):
    """The structured daily briefing output."""

    date: str
    total_count: int
    top3: list[BriefingItem] = Field(default_factory=list)
    others: list[BriefingItem] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
