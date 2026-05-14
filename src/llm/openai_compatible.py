"""OpenAI-compatible LLM client — works with Qwen, OpenAI, DeepSeek, Ollama."""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from src.llm.base import ChatResponse, ToolCall

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    """A single implementation that supports all OpenAI-compatible providers."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"LLM client initialized: model={model}, base_url={base_url}")

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> ChatResponse:
        """Send a chat completion request."""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        # Parse tool calls if any
        parsed_tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                parsed_tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        function_name=tc.function.name,
                        arguments=args,
                    )
                )

        return ChatResponse(
            content=message.content,
            tool_calls=parsed_tool_calls,
            finish_reason=choice.finish_reason or "stop",
        )
