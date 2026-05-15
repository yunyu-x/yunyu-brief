"""Twitter Agent — LLM + tool call loop for generating X tech briefings.

Similar to the email agent but specialized for analyzing trending tech tweets,
with support for topic analysis and image-aware summaries.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.llm.base import LLMClient, ChatResponse
from src.sources.twitter.models import TweetItem, TwitterBriefing

logger = logging.getLogger(__name__)

# Tool definition — let Agent request full tweet thread/context
EXPAND_TWEET_TOOL = {
    "type": "function",
    "function": {
        "name": "expand_tweet",
        "description": "Get the full content and metadata of a specific tweet by its ID. Use this when you need more context about a tweet to write a better summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to expand.",
                }
            },
            "required": ["tweet_id"],
        },
    },
}


def get_twitter_system_prompt(topics: list[str]) -> str:
    """Return the system prompt for the Twitter briefing agent.

    Args:
        topics: The configured tech topics for context.
    """
    topics_str = ", ".join(topics) if topics else "broad technology topics"

    return f"""You are TechRadar, an AI tech trend analyst for X/Twitter. Your job is to analyze a batch of trending tech tweets and produce a structured daily tech briefing in JSON format.

Your focus areas: {topics_str}

Rules:
1. Select the TOP 10 most important, insightful, or impactful tech tweets.
2. Prioritize: groundbreaking announcements > technical insights > interesting discussions > news
3. For each tweet, write a clear summary that captures the key information and why it matters.
4. If a tweet contains images/media, mention what the media shows in your summary (e.g., "配图展示了...").
5. Write summaries in Chinese (中文). Technical terms can remain in English.
6. Keep each summary to 2-3 sentences. Be informative and highlight the tech significance.
7. Generate a "trends_summary" field: a 3-5 sentence paragraph analyzing the overall tech trends you observe across all tweets.
8. Extract 5-10 trending keywords that represent today's tech hotspots.
9. The "engagement" field should be a human-readable string like "1.2k likes, 300 retweets".
10. ALWAYS include the tweet link in the output.

You MUST respond with valid JSON in this exact format:
{{
  "date": "YYYY-MM-DD",
  "total_fetched": <number of tweets you analyzed>,
  "topics": {json.dumps(topics, ensure_ascii=False)},
  "top10": [
    {{
      "title": "<concise headline summarizing the tweet>",
      "author": "<display name>",
      "author_handle": "<@handle without @>",
      "summary": "<2-3 sentence summary in Chinese, mention media if present>",
      "link": "<tweet URL>",
      "topic": "<which topic this relates to>",
      "engagement": "<e.g. 1.2k likes, 300 RT>",
      "media_urls": ["<image urls if any>"]
    }}
  ],
  "trends_summary": "<3-5 sentence analysis of today's overall tech trends in Chinese>",
  "keywords": ["keyword1", "keyword2", ...]
}}

If you need more detail about a specific tweet, use the expand_tweet tool."""


def get_twitter_user_prompt(tweets_text: str, date: str, topics: list[str]) -> str:
    """Build the user prompt with tweet data."""
    topics_display = ", ".join(topics) if topics else "general tech"
    return f"""Today is {date}. Here are the trending tech tweets I collected from X/Twitter.
Focus topics: {topics_display}

{tweets_text}

Please analyze these tweets and produce the X tech hotspot briefing JSON. 
Select the TOP 10 most significant ones and provide comprehensive analysis."""


def _build_tweets_preview(tweets: list[TweetItem], max_chars: int = 500) -> str:
    """Build a concise preview of all tweets for the initial prompt."""
    parts = []
    for tweet in tweets:
        content = tweet.content[:max_chars] if tweet.content else "(empty)"
        if len(tweet.content) > max_chars:
            content += "... [use expand_tweet tool for full content]"

        # Format engagement stats
        engagement = (
            f"Likes:{tweet.likes} RT:{tweet.retweets} "
            f"Replies:{tweet.replies} Views:{tweet.views}"
        )

        # Note media
        media_note = ""
        if tweet.media_urls:
            media_note = f"\nMedia: {len(tweet.media_urls)} image(s) attached"

        parts.append(
            f"---\n"
            f"ID: {tweet.id}\n"
            f"Author: {tweet.author} (@{tweet.author_handle})\n"
            f"Topic: {tweet.topic}\n"
            f"Date: {tweet.date.strftime('%Y-%m-%d %H:%M')}\n"
            f"Engagement: {engagement}\n"
            f"Score: {tweet.engagement_score:.0f}\n"
            f"Link: {tweet.url}\n"
            f"Content: {content}{media_note}\n"
        )
    return "\n".join(parts)


def _execute_tool(
    function_name: str, arguments: dict, tweets: list[TweetItem]
) -> str:
    """Execute a tool call and return the result string."""
    if function_name == "expand_tweet":
        tweet_id = arguments.get("tweet_id", "")
        for tweet in tweets:
            if tweet.id == tweet_id:
                media_info = ""
                if tweet.media_urls:
                    media_info = f"\n\nMedia URLs:\n" + "\n".join(tweet.media_urls)
                return (
                    f"Full content of tweet by @{tweet.author_handle}:\n\n"
                    f"{tweet.content}\n\n"
                    f"Engagement: {tweet.likes} likes, {tweet.retweets} retweets, "
                    f"{tweet.replies} replies, {tweet.views} views\n"
                    f"Link: {tweet.url}"
                    f"{media_info}"
                )
        return f"Tweet with ID '{tweet_id}' not found."
    return f"Unknown tool: {function_name}"


def _format_engagement(likes: int, retweets: int) -> str:
    """Format engagement numbers into human-readable string."""
    def fmt(n: int) -> str:
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n/1_000:.1f}k"
        return str(n)

    return f"{fmt(likes)} likes, {fmt(retweets)} RT"


def run_twitter_agent(
    llm: LLMClient,
    tweets: list[TweetItem],
    topics: list[str],
    max_turns: int = 3,
    max_preview_chars: int = 500,
    debug: bool = False,
) -> TwitterBriefing:
    """Run the Twitter agent loop to generate a tech briefing.

    Args:
        llm: LLM client instance.
        tweets: Pre-fetched and sorted tweets.
        topics: Configured tech topics.
        max_turns: Maximum LLM interaction rounds.
        max_preview_chars: Max chars per tweet in initial prompt.
        debug: Enable debug logging.

    Returns:
        TwitterBriefing with top 10 curated tech tweets.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tweets_preview = _build_tweets_preview(tweets, max_chars=max_preview_chars)

    if debug:
        logger.debug(
            f"[twitter_agent] Starting: {len(tweets)} tweets, "
            f"topics={topics}, max_turns={max_turns}"
        )
        logger.debug(
            f"[twitter_agent] Preview total length: {len(tweets_preview)} chars"
        )

    messages: list[dict] = [
        {"role": "system", "content": get_twitter_system_prompt(topics)},
        {"role": "user", "content": get_twitter_user_prompt(tweets_preview, today, topics)},
    ]
    tools = [EXPAND_TWEET_TOOL]

    if debug:
        logger.debug(f"[twitter_agent] System prompt: {len(messages[0]['content'])} chars")
        logger.debug(f"[twitter_agent] User prompt: {len(messages[1]['content'])} chars")

    response: ChatResponse | None = None

    for turn in range(max_turns):
        logger.info(f"Twitter agent turn {turn + 1}/{max_turns}")

        if debug:
            logger.debug(
                f"[twitter_agent] Turn {turn + 1}: "
                f"sending {len(messages)} messages to LLM..."
            )

        response = llm.chat(messages, tools=tools)

        if debug:
            logger.debug(f"[twitter_agent] Turn {turn + 1} response:")
            logger.debug(f"[twitter_agent]   finish_reason: {response.finish_reason}")
            logger.debug(f"[twitter_agent]   tool_calls: {len(response.tool_calls)}")

        # If LLM made tool calls, execute them and continue
        if response.tool_calls:
            if debug:
                logger.debug(
                    f"[twitter_agent] Processing {len(response.tool_calls)} tool call(s)..."
                )

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

            for tc in response.tool_calls:
                if debug:
                    logger.debug(
                        f"[twitter_agent]   Tool: {tc.function_name}({json.dumps(tc.arguments)})"
                    )

                result = _execute_tool(tc.function_name, tc.arguments, tweets)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                logger.info(f"Tool call: {tc.function_name}({tc.arguments})")
            continue

        # No tool calls — parse the JSON response
        if response.content:
            if debug:
                logger.debug("[twitter_agent] Parsing final response as JSON...")
            briefing = _parse_twitter_briefing(
                response.content, today, len(tweets), topics, debug=debug
            )
            if debug:
                logger.debug(
                    f"[twitter_agent] Briefing parsed: "
                    f"top10={len(briefing.top10)}, keywords={briefing.keywords}"
                )
            return briefing

    # Fallback if max turns exceeded
    logger.warning("Twitter agent exceeded max turns, attempting to parse last response")
    if response and response.content:
        return _parse_twitter_briefing(
            response.content, today, len(tweets), topics, debug=debug
        )

    return TwitterBriefing(date=today, total_fetched=len(tweets), topics=topics)


def _parse_twitter_briefing(
    content: str,
    date: str,
    total_fetched: int,
    topics: list[str],
    debug: bool = False,
) -> TwitterBriefing:
    """Parse LLM response content into TwitterBriefing."""
    try:
        text = content.strip()
        # Remove markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]

        if debug:
            logger.debug(f"[twitter_agent] Parsing JSON ({len(text.strip())} chars)...")

        data = json.loads(text.strip())

        if debug:
            logger.debug(f"[twitter_agent] JSON keys: {list(data.keys())}")

        return TwitterBriefing(**data)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to parse Twitter briefing JSON: {e}")
        if debug:
            logger.debug(f"[twitter_agent] Parse error: {type(e).__name__}: {e}")
            logger.debug(f"[twitter_agent] Raw (first 1000):\n{content[:1000]}")
        return TwitterBriefing(date=date, total_fetched=total_fetched, topics=topics)
