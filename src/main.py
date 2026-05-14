"""Paperboy — main entry point.

Usage:
    python -m src.main          # Run full pipeline (requires .env or env vars)
    python -m src.main --demo   # Demo mode (no config needed, shows sample output)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import Settings, get_settings
from src.models import DailyBriefing, EmailItem

logger = logging.getLogger("paperboy")


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def run_demo() -> None:
    """Run in demo mode — no Gmail, no LLM, just show a beautiful sample briefing."""
    from src.summarizer import render_briefing_html, render_briefing_text

    demo_path = Path(__file__).parent.parent / "examples" / "demo_output.json"
    demo_data = json.loads(demo_path.read_text(encoding="utf-8"))
    briefing = DailyBriefing(**demo_data)

    text_output = render_briefing_text(briefing)
    html_output = render_briefing_html(briefing)

    # Print to terminal
    print(text_output)

    # Save HTML for preview
    output_path = Path("demo_output.html")
    output_path.write_text(html_output, encoding="utf-8")
    print(f"\n💡 HTML version saved to: {output_path.absolute()}")
    print("   Open it in your browser to see the email preview!")


def run_pipeline(settings: Settings) -> None:
    """Run the full pipeline: fetch → agent → summarize → send."""
    from src.agent import run_agent
    from src.llm.openai_compatible import OpenAICompatibleClient
    from src.sources.gmail import GmailSource
    from src.sinks.email import EmailSink
    from src.summarizer import render_briefing_html, render_briefing_text

    # 1. Fetch emails
    logger.info("Step 1/4: Fetching emails...")
    source = GmailSource(
        address=settings.gmail_address,
        app_password=settings.gmail_app_password,
        label=settings.gmail_label,
        lookback_hours=settings.lookback_hours,
    )
    emails = source.fetch()

    if not emails:
        logger.info("No newsletter emails found in the last "
                    f"{settings.lookback_hours} hours. Skipping.")
        return

    # 2. Run agent (LLM)
    logger.info(f"Step 2/4: Running agent on {len(emails)} emails...")
    llm_config = settings.get_llm_config()
    llm = OpenAICompatibleClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config["model"],
    )
    briefing = run_agent(
        llm=llm,
        emails=emails,
        max_turns=settings.max_agent_turns,
        max_preview_chars=settings.max_email_preview_chars,
    )

    # 3. Render
    logger.info("Step 3/4: Rendering briefing...")
    html_content = render_briefing_html(briefing)
    text_content = render_briefing_text(briefing)

    # 4. Send
    logger.info("Step 4/4: Sending briefing email...")
    sink = EmailSink(
        address=settings.gmail_address,
        app_password=settings.gmail_app_password,
    )
    sink.send(briefing, html_content, text_content)

    logger.info("✅ Daily briefing sent successfully!")


def cli() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="paperboy",
        description="📬 Your AI paperboy — turns newsletter chaos into a 30-second morning briefing.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode (no config needed, shows sample output)",
    )
    args = parser.parse_args()

    setup_logging()

    if args.demo:
        logger.info("Running in DEMO mode...")
        run_demo()
        return

    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file or environment variables.")
        logger.error("Run with --demo flag to see a sample output without config.")
        sys.exit(1)

    # Validate required settings
    if not settings.gmail_address or not settings.gmail_app_password:
        logger.error("GMAIL_ADDRESS and GMAIL_APP_PASSWORD are required.")
        logger.error("See .env.example for configuration template.")
        sys.exit(1)

    llm_config = settings.get_llm_config()
    if not llm_config["api_key"]:
        logger.error(f"API key for provider '{settings.llm_provider.value}' is not set.")
        sys.exit(1)

    run_pipeline(settings)


if __name__ == "__main__":
    cli()
