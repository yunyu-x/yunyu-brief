"""Twitter Summarizer — renders Twitter briefings into H5 page + email digest.

Strategy:
- Generate a full interactive H5 page (saved to disk / deployed to static hosting)
- Generate a lightweight email digest (top 3 + trends + CTA button to H5 page)
- Keep plain text fallback for email clients that don't support HTML
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.sources.twitter.models import TwitterBriefing

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_twitter_h5_page(briefing: TwitterBriefing) -> str:
    """Render the full interactive H5 page with all top 10 items.

    This is the primary viewing experience — supports full CSS3, animations,
    dark/light mode, responsive design, and rich media.
    """
    template_path = TEMPLATES_DIR / "twitter_h5.html"
    template_str = template_path.read_text(encoding="utf-8")

    # Build topic tags
    topics_html = "\n".join(
        f'            <span class="topic-tag">📌 {topic}</span>'
        for topic in briefing.topics
    )

    # Build top 10 tweet cards
    gradients = [
        "linear-gradient(135deg, #f093fb, #f5576c)",
        "linear-gradient(135deg, #667eea, #764ba2)",
        "linear-gradient(135deg, #4facfe, #00f2fe)",
    ]
    top10_html = ""
    for i, item in enumerate(briefing.top10, 1):
        # Avatar with first character
        avatar_char = item.author[0].upper() if item.author else "?"
        avatar_gradient = gradients[(i - 1) % len(gradients)]

        # Media image
        media_html = ""
        if item.media_urls:
            media_html = (
                f'<img class="media-img" src="{item.media_urls[0]}" '
                f'alt="tweet media" onerror="this.style.display=\'none\'">'
            )

        # Topic badge
        topic_html = ""
        if item.topic:
            topic_html = f'<span class="topic-badge">{item.topic}</span>'

        # Engagement
        engagement_html = ""
        if item.engagement:
            engagement_html = f'<span class="engagement">❤️ {item.engagement}</span>'

        top10_html += f"""
            <div class="tweet-card fade-in">
                <span class="rank">{i}</span>
                <div class="card-header">
                    <div class="avatar" style="background: {avatar_gradient};">{avatar_char}</div>
                    <div class="author-info">
                        <div class="author-name">{item.author}</div>
                        <div class="author-handle">@{item.author_handle}</div>
                    </div>
                    {topic_html}
                </div>
                <div class="title">{item.title}</div>
                <div class="summary">{item.summary}</div>
                {media_html}
                <div class="card-footer">
                    {engagement_html}
                    <a href="{item.link}" target="_blank" rel="noopener" class="view-link">
                        查看原文 →
                    </a>
                </div>
            </div>"""

    # Keywords
    keywords_html = "\n".join(
        f'                <span class="keyword-chip">{kw}</span>'
        for kw in briefing.keywords
    )

    # Template substitution
    html = template_str.replace("{{DATE}}", briefing.date)
    html = html.replace("{{TOTAL_FETCHED}}", str(briefing.total_fetched))
    html = html.replace("{{TOPICS_TAGS}}", topics_html)
    html = html.replace("{{TRENDS_SUMMARY}}", briefing.trends_summary or "暂无趋势分析")
    html = html.replace("{{TOP10_ITEMS}}", top10_html)
    html = html.replace("{{KEYWORDS}}", keywords_html)

    return html


def render_twitter_email_digest(briefing: TwitterBriefing, h5_url: str = "") -> str:
    """Render the lightweight email digest (top 3 preview + CTA to full page).

    This is designed for email clients — uses table-based layout, inline styles,
    and minimal content to drive clicks to the H5 page.
    """
    template_path = TEMPLATES_DIR / "twitter_email_digest.html"
    template_str = template_path.read_text(encoding="utf-8")

    # Build top 3 preview items
    top3_html = ""
    for i, item in enumerate(briefing.top10[:3], 1):
        # Engagement badge
        engagement_note = ""
        if item.engagement:
            engagement_note = (
                f'<span style="color: #f87171; font-size: 11px; margin-left: 6px;">'
                f'❤️ {item.engagement}</span>'
            )

        # Topic
        topic_note = ""
        if item.topic:
            topic_note = (
                f'<span style="display: inline-block; background: rgba(16,185,129,0.15); '
                f'color: #34d399; padding: 2px 8px; border-radius: 8px; font-size: 10px; '
                f'margin-left: 6px;">{item.topic}</span>'
            )

        top3_html += f"""
                                <tr>
                                    <td style="padding: 14px 16px; border-bottom: 1px solid #334155; border-radius: 8px;">
                                        <div style="font-size: 14px; font-weight: 600; color: #f1f5f9; margin-bottom: 4px;">
                                            <span style="color: #60a5fa; margin-right: 6px;">{i}.</span>{item.title}{topic_note}
                                        </div>
                                        <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">
                                            @{item.author_handle}{engagement_note}
                                        </div>
                                        <div style="font-size: 13px; color: #94a3b8; line-height: 1.5;">
                                            {item.summary[:120]}{'...' if len(item.summary) > 120 else ''}
                                        </div>
                                    </td>
                                </tr>"""

    # Keywords as inline text
    keywords_text = " · ".join(
        f'<span style="display: inline-block; background: rgba(245,158,11,0.1); '
        f'color: #fbbf24; padding: 2px 8px; border-radius: 8px; font-size: 11px; '
        f'margin: 2px 3px;">{kw}</span>'
        for kw in briefing.keywords[:8]
    )

    # Fallback URL if h5_url not provided
    if not h5_url:
        h5_url = "#"

    # Template substitution
    html = template_str.replace("{{DATE}}", briefing.date)
    html = html.replace("{{TOTAL_FETCHED}}", str(briefing.total_fetched))
    html = html.replace("{{TRENDS_SUMMARY}}", briefing.trends_summary or "暂无趋势分析")
    html = html.replace("{{TOP3_PREVIEW}}", top3_html)
    html = html.replace("{{KEYWORDS}}", keywords_text)
    html = html.replace("{{H5_URL}}", h5_url)

    return html


def render_twitter_briefing_text(briefing: TwitterBriefing, h5_url: str = "") -> str:
    """Render Twitter briefing as plain text (fallback for email clients)."""
    template_path = TEMPLATES_DIR / "twitter_briefing.txt"
    template_str = template_path.read_text(encoding="utf-8")

    # Topics
    topics_text = " / ".join(briefing.topics)

    # Top 10 items
    top10_lines = []
    for i, item in enumerate(briefing.top10, 1):
        media_note = f"\n   [含 {len(item.media_urls)} 张配图]" if item.media_urls else ""
        engagement_note = f" ({item.engagement})" if item.engagement else ""
        top10_lines.append(
            f"{i}. {item.title}\n"
            f"   @{item.author_handle} ({item.author}){engagement_note}\n"
            f"   {item.summary}{media_note}\n"
            f"   -> {item.link}\n"
            f"   #{item.topic}"
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

    if h5_url:
        text += f"\n\n🌐 查看完整图文简报: {h5_url}\n"

    return text
