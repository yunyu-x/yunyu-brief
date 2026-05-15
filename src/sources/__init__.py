"""Source plugins — fetch content from various inputs."""

from src.sources.base import Source

__all__ = ["Source", "GmailSource", "TwitterSource"]


def __getattr__(name: str):
    """Lazy imports to avoid loading heavy dependencies at module level."""
    if name == "GmailSource":
        from src.sources.gmail import GmailSource
        return GmailSource
    if name == "TwitterSource":
        from src.sources.twitter import TwitterSource
        return TwitterSource
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
