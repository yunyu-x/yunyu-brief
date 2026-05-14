"""Source plugin protocol."""

from __future__ import annotations

from typing import Protocol

from src.models import EmailItem


class Source(Protocol):
    """Protocol for data source plugins.

    Implement this to add new sources (RSS, Twitter, etc.)
    """

    def fetch(self) -> list[EmailItem]:
        """Fetch items from the source.

        Returns:
            List of EmailItem objects to be summarized.
        """
        ...
