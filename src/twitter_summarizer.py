"""Twitter Summarizer — renders Twitter briefings into HTML and text email content."""

from __future__ import annotations

import logging
from pathlib import Path

from src.sources.twitter.models import TwitterBriefing

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_twitter_briefing_html(briefing: TwitterBriefing) -> str:
    """Render Twitter briefing as HTML email with images and rich formatting."""
    template_path = TEMPLATES_DIR / "twitter_briefing.html"
    template_str = template_path.read_text(encoding="utf-8")

    # Build topics tags
    topics_tags = " ".join(
        f'<span style="display: inline-block; background: #eff6ff; color: #2563eb; '
        f'padding: 4px 12px; border-radius: 16px; font-size: 12px; '
        f'margin: 2px 4px 2px 0; font-weight: 500;">{topic}</span>'
        for topic in briefing.topics
    )

    # Build top 10 items HTML
    top10_html = ""
    for i, item in enumerate(briefing.top10, 1):
        # Media section — show first image if available
        media_html = ""
        if item.media_urls:
            media_html = f"""
                <div style="margin-top: 10px; border-radius: 8px; overflow: hidden;">
                    <img src="{item.media_urls[0]}" alt="tweet media" 
                         style="width: 100%; max-height: 200px; object-fit: cover; border-radius: 8px;"
                         onerror="this.style.display='none'">
                </div>"""

        # Topic badge
        topic_badge = ""
        if item.topic:
            topic_badge = (
                f'<span style="background: #f0fdf4; color: #16a34a; '
                f'padding: 2px 8px; border-radius: 10px; font-size: 11px; '
                f'margin-left: 8px;">{item.topic}</span>'
            )

        # Engagement badge
        engagement_html = ""
        if item.engagement:
            engagement_html = (
                f'<span style="color: #ef4444; font-size: 12px; margin-left: 8px;">'
                f'❤️ {item.engagement}</span>'
            )

        top10_html += f"""
                <tr>
                    <td style="padding: 16px 0; border-bottom: 1px solid #f1f5f9;">
                        <div style="display: flex; align-items: flex-start;">
                            <div style="min-width: 28px; height: 28px; background: #1e293b; color: #fff; border-radius: 50%; text-align: center; line-height: 28px; font-size: 13px; font-weight: 600; margin-right: 12px;">{i}</div>
                            <div style="flex: 1;">
                                <div style="font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 4px;">
                                    {item.title}{topic_badge}
                                </div>
                                <div style="font-size: 13px; color: #64748b; margin-bottom: 6px;">
                                    <strong>@{item.author_handle}</strong> ({item.author}){engagement_html}
                                </div>
                                <div style="font-size: 14px; color: #374151; line-height: 1.6; margin-bottom: 8px;">
                                    {item.summary}
                                </div>{media_html}
                                <div style="margin-top: 8px;">
                                    <a href="{item.link}" style="color: #2563eb; font-size: 13px; text-decoration: none; font-weight: 500;">
                                        🔗 查看原文 →
                                    </a>
                                </div>
                            </div>
                        </div>
                    </td>
                </tr>"""

    # Keywords
    keywords_html = " ".join(
        f'<span style="display: inline-block; background: #fef3c7; color: #d97706; '
        f'padding: 3px 10px; border-radius: 12px; font-size: 12px; '
        f'margin: 2px 4px 2px 0;">{kw}</span>'
        for kw in briefing.keywords
    )

    # Template substitution
    html = template_str.replace("{{DATE}}", briefing.date)
    html = html.replace("{{TOTAL_FETCHED}}", str(briefing.total_fetched))
    html = html.replace("{{TOPICS_TAGS}}", topics_tags)
    html = html.replace("{{TRENDS_SUMMARY}}", briefing.trends_summary or "暂无趋势分析")
    html = html.replace("{{TOP10_ITEMS}}", top10_html)
    html = html.replace("{{KEYWORDS}}", keywords_html)

    return html


def render_twitter_briefing_text(briefing: TwitterBriefing) -> str:
    """Render Twitter briefing as plain text email."""
    template_path = TEMPLATES_DIR / "twitter_briefing.txt"
    template_str = template_path.read_text(encoding="utf-8")

    # Topics
    topics_text = " / ".join(briefing.topics)

    # Top 10 items
    top10_lines = []
    for i, item in enumerate(briefing.top10, 1):
        media_note = f"\n   📷 含 {len(item.media_urls)} 张配图" if item.media_urls else ""
        engagement_note = f" ({item.engagement})" if item.engagement else ""
        top10_lines.append(
            f"{i}. {item.title}\n"
            f"   @{item.author_handle} ({item.author}){engagement_note}\n"
            f"   {item.summary}{media_note}\n"
            f"   🔗 {item.link}\n"
            f"   话题: {item.topic}"
        )

    # Keywords
    keywords_text = " / ".join(briefing.keywords)

    # Template substitution
    text = template_str.replace("{{DATE}}", briefing.date)
    text = text.replace("{{TOTAL_FETCHED}}", str(briefing.total_fetched))
    text = text.replace("{{TOPICS}}", topics_text)
    text = text.replace("{{TRENDS_SUMMARY}}", briefing.trends_summary or "暂无趋势分析")
    text = text.replace("{{TOP10_ITEMS}}", "\n\n".join(top10_lines))
    text = text.replace("{{KEYWORDS}}", keywords_text)

    return text
