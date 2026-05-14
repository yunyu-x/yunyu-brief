"""Source plugins — fetch content from various inputs."""

from src.sources.base import Source
from src.sources.gmail import GmailSource

__all__ = ["Source", "GmailSource"]
