"""Sink plugin protocol."""

from __future__ import annotations

from typing import Protocol

from src.models import DailyBriefing


class Sink(Protocol):
    """Protocol for delivery sink plugins.

    Implement this to add new channels (Telegram, Feishu, etc.)
    """

    def send(self, briefing: DailyBriefing, html_content: str, text_content: str) -> None:
        """Send the briefing to the destination.

        Args:
            briefing: The structured briefing data.
            html_content: Rendered HTML version.
            text_content: Rendered plain text version.
        """
        ...
