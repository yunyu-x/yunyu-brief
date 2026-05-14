"""LLM client protocol definition."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str
    content: str | None = None
    tool_calls: list[Any] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ToolCall(BaseModel):
    """A tool call requested by the LLM."""

    id: str
    function_name: str
    arguments: dict


class ChatResponse(BaseModel):
    """Response from LLM."""

    content: str | None = None
    tool_calls: list[ToolCall] = []
    finish_reason: str = "stop"


class LLMClient(Protocol):
    """Protocol for LLM clients. All providers must implement this."""

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> ChatResponse: ...
