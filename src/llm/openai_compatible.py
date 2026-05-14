"""OpenAI-compatible LLM client — works with Qwen, OpenAI, DeepSeek, Ollama."""

from __future__ import annotations

import json
import logging
import time

from openai import OpenAI

from src.llm.base import ChatResponse, ToolCall

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    """A single implementation that supports all OpenAI-compatible providers."""

    def __init__(self, api_key: str, base_url: str, model: str, debug: bool = False):
        self.model = model
        self.debug = debug
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self._call_count = 0
        logger.info(f"LLM client initialized: model={model}, base_url={base_url}")

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> ChatResponse:
        """Send a chat completion request."""
        self._call_count += 1
        call_id = self._call_count

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if self.debug:
            logger.debug(f"[LLM] ─── Request #{call_id} ───")
            logger.debug(f"[LLM]   Model: {self.model}")
            logger.debug(f"[LLM]   Messages: {len(messages)} messages")
            logger.debug(f"[LLM]   Tools: {[t['function']['name'] for t in tools] if tools else 'None'}")
            logger.debug(f"[LLM]   Temperature: 0.3")
            total_chars = sum(len(m.get("content", "") or "") for m in messages)
            logger.debug(f"[LLM]   Total input chars: {total_chars}")
            # Log each message role/length
            for i, m in enumerate(messages):
                content_len = len(m.get("content", "") or "")
                logger.debug(
                    f"[LLM]   msg[{i}] role={m['role']} len={content_len}"
                )

        start_time = time.time()

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            if self.debug:
                elapsed = time.time() - start_time
                logger.debug(f"[LLM] ❌ Request #{call_id} FAILED after {elapsed:.2f}s")
                logger.debug(f"[LLM] ❌ Error: {type(e).__name__}: {e}")
            raise

        elapsed = time.time() - start_time
        choice = response.choices[0]
        message = choice.message

        if self.debug:
            logger.debug(f"[LLM] ─── Response #{call_id} ({elapsed:.2f}s) ───")
            logger.debug(f"[LLM]   Finish reason: {choice.finish_reason}")
            logger.debug(f"[LLM]   Content length: {len(message.content) if message.content else 0}")
            logger.debug(f"[LLM]   Tool calls: {len(message.tool_calls) if message.tool_calls else 0}")
            if hasattr(response, "usage") and response.usage:
                logger.debug(
                    f"[LLM]   Tokens: prompt={response.usage.prompt_tokens}, "
                    f"completion={response.usage.completion_tokens}, "
                    f"total={response.usage.total_tokens}"
                )
            if message.content:
                preview = message.content[:500]
                logger.debug(f"[LLM]   Content preview: {preview}{'...' if len(message.content) > 500 else ''}")

        # Parse tool calls if any
        parsed_tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}

                if self.debug:
                    logger.debug(
                        f"[LLM]   Tool call: {tc.function.name}({tc.function.arguments})"
                    )

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
