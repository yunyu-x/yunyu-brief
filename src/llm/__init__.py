"""LLM abstraction layer — multi-provider support via OpenAI-compatible protocol."""

from src.llm.base import LLMClient
from src.llm.openai_compatible import OpenAICompatibleClient

__all__ = ["LLMClient", "OpenAICompatibleClient"]
