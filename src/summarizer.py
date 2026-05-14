"""Summarizer — prompt engineering and briefing assembly."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template

from src.models import DailyBriefing

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def get_system_prompt() -> str:
    """Return the system prompt for the briefing agent."""
    return """You are Paperboy, an AI newsletter curator. Your job is to analyze a batch of newsletter emails and produce a structured daily briefing in JSON format.

Rules:
1. Pick the TOP 3 most important/interesting items for the "top3" section.
2. Summarize remaining items briefly in the "others" section.
3. Extract 3-7 trending keywords across all emails for the "keywords" section.
4. Write summaries in the SAME LANGUAGE as the original email content. If mixed, prefer Chinese.
5. Keep each summary to 1-2 sentences. Be concise but informative.
6. If an email has a link, include it. Otherwise leave link empty.

You MUST respond with valid JSON in this exact format:
{
  "date": "YYYY-MM-DD",
  "total_count": <number>,
  "top3": [
    {"title": "...", "source": "...", "summary": "...", "link": "..."}
  ],
  "others": [
    {"title": "...", "source": "...", "summary": "...", "link": "..."}
  ],
  "keywords": ["keyword1", "keyword2", ...]
}

If you need more detail about a specific email, use the expand_email tool."""


def get_user_prompt(emails_text: str, date: str) -> str:
    """Build the user prompt with email previews."""
    return f"""Today is {date}. Here are the newsletter emails to summarize:

{emails_text}

Please analyze these emails and produce the daily briefing JSON."""


def render_briefing_html(briefing: DailyBriefing) -> str:
    """Render briefing as HTML email."""
    template_path = TEMPLATES_DIR / "briefing.html"
    template_str = template_path.read_text(encoding="utf-8")

    # Build top3 HTML
    top3_html = ""
    for i, item in enumerate(briefing.top3, 1):
        link_html = f' <a href="{item.link}" style="color: #2563eb;">[原文]</a>' if item.link else ""
        top3_html += f"""
        <tr>
            <td style="padding: 12px 0; border-bottom: 1px solid #f0f0f0;">
                <div style="font-size: 16px; font-weight: 600; color: #1a1a1a;">
                    {i}. {item.title}
                </div>
                <div style="font-size: 14px; color: #555; margin-top: 4px;">
                    {item.summary}{link_html}
                </div>
                <div style="font-size: 12px; color: #999; margin-top: 2px;">
                    来源：{item.source}
                </div>
            </td>
        </tr>"""

    # Build others HTML
    others_html = ""
    for item in briefing.others:
        link_html = f' <a href="{item.link}" style="color: #2563eb;">[链接]</a>' if item.link else ""
        others_html += f"""
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #f8f8f8;">
                <div style="font-size: 14px; color: #333;">
                    <strong>{item.source}</strong> {item.title}：{item.summary}{link_html}
                </div>
            </td>
        </tr>"""

    # Keywords
    keywords_html = " / ".join(
        f'<span style="background: #f0f4ff; color: #2563eb; padding: 2px 8px; '
        f'border-radius: 12px; font-size: 13px;">{kw}</span>'
        for kw in briefing.keywords
    )

    # Template substitution
    html = template_str.replace("{{DATE}}", briefing.date)
    html = html.replace("{{TOTAL_COUNT}}", str(briefing.total_count))
    html = html.replace("{{TOP3_ITEMS}}", top3_html)
    html = html.replace("{{OTHER_ITEMS}}", others_html)
    html = html.replace("{{KEYWORDS}}", keywords_html)

    return html


def render_briefing_text(briefing: DailyBriefing) -> str:
    """Render briefing as plain text."""
    template_path = TEMPLATES_DIR / "briefing.txt"
    template_str = template_path.read_text(encoding="utf-8")

    # Build top3 text
    top3_lines = []
    for i, item in enumerate(briefing.top3, 1):
        link = f"\n   原文: {item.link}" if item.link else ""
        top3_lines.append(
            f"{i}. {item.title}\n   {item.summary}\n   来源: {item.source}{link}"
        )

    # Build others text
    others_lines = []
    for item in briefing.others:
        link = f" [{item.link}]" if item.link else ""
        others_lines.append(f"- [{item.source}] {item.title}: {item.summary}{link}")

    # Keywords
    keywords_text = " / ".join(briefing.keywords)

    text = template_str.replace("{{DATE}}", briefing.date)
    text = text.replace("{{TOTAL_COUNT}}", str(briefing.total_count))
    text = text.replace("{{TOP3_ITEMS}}", "\n".join(top3_lines))
    text = text.replace("{{OTHER_ITEMS}}", "\n".join(others_lines))
    text = text.replace("{{KEYWORDS}}", keywords_text)

    return text
