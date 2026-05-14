"""Smoke tests — ensure imports work and demo mode runs."""

import json
from pathlib import Path


def test_imports():
    """All modules should import without error."""
    from src.config import Settings, LLMProvider
    from src.models import EmailItem, DailyBriefing, BriefingItem
    from src.llm.base import LLMClient, ChatResponse, ToolCall
    from src.llm.openai_compatible import OpenAICompatibleClient
    from src.sources.base import Source
    from src.sources.gmail import GmailSource
    from src.sinks.base import Sink
    from src.sinks.email import EmailSink
    from src.agent import run_agent, EXPAND_EMAIL_TOOL
    from src.summarizer import (
        get_system_prompt,
        render_briefing_html,
        render_briefing_text,
    )


def test_demo_data_valid():
    """Demo data file should be valid JSON and parseable as DailyBriefing."""
    from src.models import DailyBriefing

    demo_path = Path(__file__).parent.parent / "examples" / "demo_output.json"
    data = json.loads(demo_path.read_text(encoding="utf-8"))
    briefing = DailyBriefing(**data)

    assert briefing.date == "2026-05-14"
    assert briefing.total_count == 8
    assert len(briefing.top3) == 3
    assert len(briefing.others) == 5
    assert len(briefing.keywords) >= 3


def test_render_briefing():
    """Rendering should produce non-empty output."""
    from src.models import DailyBriefing
    from src.summarizer import render_briefing_html, render_briefing_text

    demo_path = Path(__file__).parent.parent / "examples" / "demo_output.json"
    data = json.loads(demo_path.read_text(encoding="utf-8"))
    briefing = DailyBriefing(**data)

    html = render_briefing_html(briefing)
    text = render_briefing_text(briefing)

    assert "每日简报" in html
    assert "2026-05-14" in html
    assert "GPT-5" in html

    assert "每日简报" in text
    assert "Top 3" in text
    assert "GPT-5" in text


def test_config_defaults():
    """Settings should have sensible defaults."""
    import os

    # Set minimal required env vars for testing
    os.environ.setdefault("GMAIL_ADDRESS", "test@gmail.com")
    os.environ.setdefault("GMAIL_APP_PASSWORD", "test-password")
    os.environ.setdefault("QWEN_API_KEY", "sk-test")

    from src.config import Settings, LLMProvider

    settings = Settings(
        gmail_address="test@gmail.com",
        gmail_app_password="test",
        qwen_api_key="sk-test",
    )
    assert settings.llm_provider == LLMProvider.QWEN
    assert settings.gmail_label == "Newsletters"
    assert settings.lookback_hours == 24

    config = settings.get_llm_config()
    assert "dashscope" in config["base_url"]
    assert config["model"] == "qwen-plus"
