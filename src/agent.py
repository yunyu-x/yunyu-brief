"""Minimal Agent — LLM + tool call loop for generating briefings."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.llm.base import LLMClient, ChatResponse
from src.models import DailyBriefing, EmailItem
from src.summarizer import get_system_prompt, get_user_prompt

logger = logging.getLogger(__name__)

# Tool definition for the LLM
EXPAND_EMAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "expand_email",
        "description": "Get the full body text of a specific email by its ID. Use this when you need more detail about an email to write a better summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The ID of the email to expand.",
                }
            },
            "required": ["email_id"],
        },
    },
}


def _build_emails_preview(emails: list[EmailItem], max_chars: int = 500) -> str:
    """Build a concise preview of all emails for the initial prompt."""
    parts = []
    for email in emails:
        preview = email.body_text[:max_chars] if email.body_text else "(empty)"
        if len(email.body_text) > max_chars:
            preview += "... [use expand_email tool for full content]"
        parts.append(
            f"---\n"
            f"ID: {email.id}\n"
            f"Subject: {email.subject}\n"
            f"From: {email.sender}\n"
            f"Date: {email.date.strftime('%Y-%m-%d %H:%M')}\n"
            f"Preview: {preview}\n"
        )
    return "\n".join(parts)


def _execute_tool(
    function_name: str, arguments: dict, emails: list[EmailItem]
) -> str:
    """Execute a tool call and return the result string."""
    if function_name == "expand_email":
        email_id = arguments.get("email_id", "")
        for email in emails:
            if email.id == email_id:
                return f"Full content of '{email.subject}':\n\n{email.body_text}"
        return f"Email with ID '{email_id}' not found."
    return f"Unknown tool: {function_name}"


def run_agent(
    llm: LLMClient,
    emails: list[EmailItem],
    max_turns: int = 3,
    max_preview_chars: int = 500,
) -> DailyBriefing:
    """Run the minimal agent loop to generate a daily briefing.

    The agent can use the expand_email tool to get full content of specific
    emails when the preview is not enough for a good summary.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    emails_preview = _build_emails_preview(emails, max_chars=max_preview_chars)

    messages: list[dict] = [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": get_user_prompt(emails_preview, today)},
    ]
    tools = [EXPAND_EMAIL_TOOL]

    for turn in range(max_turns):
        logger.info(f"Agent turn {turn + 1}/{max_turns}")
        response: ChatResponse = llm.chat(messages, tools=tools)

        # If LLM made tool calls, execute them and continue
        if response.tool_calls:
            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ],
            })

            # Execute each tool call and add results
            for tc in response.tool_calls:
                result = _execute_tool(tc.function_name, tc.arguments, emails)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                logger.info(f"Tool call: {tc.function_name}({tc.arguments})")
            continue

        # No tool calls — parse the JSON response
        if response.content:
            return _parse_briefing(response.content, today, len(emails))

    # Fallback: if max turns exceeded, try to parse whatever we have
    logger.warning("Agent exceeded max turns, attempting to parse last response")
    if response.content:
        return _parse_briefing(response.content, today, len(emails))

    # Ultimate fallback
    return DailyBriefing(date=today, total_count=len(emails))


def _parse_briefing(content: str, date: str, total_count: int) -> DailyBriefing:
    """Parse LLM response content into DailyBriefing."""
    try:
        # Try to extract JSON from the response (handle markdown code blocks)
        text = content.strip()
        if text.startswith("```"):
            # Remove markdown code fence
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(text.strip())
        return DailyBriefing(**data)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to parse briefing JSON: {e}")
        logger.debug(f"Raw content: {content[:500]}")
        # Return a minimal briefing
        return DailyBriefing(date=date, total_count=total_count)
