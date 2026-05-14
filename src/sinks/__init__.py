"""Sink plugins — deliver briefings to various channels."""

from src.sinks.base import Sink
from src.sinks.email import EmailSink

__all__ = ["Sink", "EmailSink"]
