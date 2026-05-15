"""Paperboy — main entry point.

Usage:
    python -m src.main          # Run full pipeline (requires .env or env vars)
    python -m src.main --demo   # Demo mode (no config needed, shows sample output)
    DEBUG=true python -m src.main  # Full pipeline tracing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.config import Settings, get_settings
from src.models import DailyBriefing, EmailItem

logger = logging.getLogger("paperboy")


class PipelineTracer:
    """Tracks timing and status for each pipeline step."""

    def __init__(self):
        self.steps: list[dict] = []
        self._current_step: str | None = None
        self._step_start: float = 0
        self.pipeline_start: float = time.time()

    def start_step(self, name: str, details: str = "") -> None:
        self._current_step = name
        self._step_start = time.time()
        logger.info(f"{'='*60}")
        logger.info(f"[TRACE] ▶ STEP: {name}")
        if details:
            logger.info(f"[TRACE]   Details: {details}")
        logger.info(f"{'='*60}")

    def end_step(self, status: str = "OK", summary: str = "") -> None:
        elapsed = time.time() - self._step_start
        icon = "✅" if status == "OK" else "❌" if status == "FAIL" else "⚠️"
        step_record = {
            "step": self._current_step,
            "status": status,
            "elapsed_sec": round(elapsed, 2),
            "summary": summary,
        }
        self.steps.append(step_record)
        logger.info(f"[TRACE] {icon} {self._current_step} — {status} ({elapsed:.2f}s)")
        if summary:
            logger.info(f"[TRACE]   Summary: {summary}")

    def print_report(self) -> None:
        total = time.time() - self.pipeline_start
        logger.info("")
        logger.info(f"{'='*60}")
        logger.info(f"[TRACE] 📊 PIPELINE REPORT")
        logger.info(f"{'='*60}")
        for s in self.steps:
            icon = "✅" if s["status"] == "OK" else "❌" if s["status"] == "FAIL" else "⚠️"
            logger.info(
                f"[TRACE]  {icon} {s['step']:<30} {s['status']:<6} {s['elapsed_sec']:.2f}s  {s['summary']}"
            )
        logger.info(f"{'─'*60}")
        logger.info(f"[TRACE]  ⏱️  Total pipeline time: {total:.2f}s")
        logger.info(f"{'='*60}")


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    if debug:
        logger.info("[DEBUG MODE] Full pipeline tracing enabled")
        logger.info(f"[DEBUG MODE] Timestamp: {datetime.now(timezone.utc).isoformat()}")


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


def run_twitter_pipeline(settings: Settings) -> None:
    """Run the Twitter/X pipeline: fetch → agent → render H5 → send digest email.

    Output strategy:
    1. Generate a full interactive H5 page (saved to output dir)
    2. Send a lightweight email digest with top 3 + link to full H5 page
    """
    from src.llm.openai_compatible import OpenAICompatibleClient
    from src.sinks.email import EmailSink
    from src.sources.twitter import TwitterSource
    from src.twitter_agent import run_twitter_agent
    from src.twitter_summarizer import (
        render_twitter_h5_page,
        render_twitter_email_digest,
        render_twitter_briefing_text,
    )

    debug = settings.debug
    tracer = PipelineTracer() if debug else None

    # ─── Step 1: Fetch Tweets ──────────────────────────────────────
    topics = settings.get_twitter_topics()
    if tracer:
        tracer.start_step(
            "1. FETCH TWEETS",
            f"Topics={topics or 'defaults'}, "
            f"Lookback={settings.twitter_lookback_hours}h, "
            f"TopPerTopic={settings.twitter_top_per_topic}",
        )

    logger.info("Step 1/5: Fetching trending tweets from X...")
    source = TwitterSource(
        topics=topics or None,
        lookback_hours=settings.twitter_lookback_hours,
        top_per_topic=settings.twitter_top_per_topic,
        final_top=settings.twitter_final_top,
        twikit_username=settings.twikit_username,
        twikit_email=settings.twikit_email,
        twikit_password=settings.twikit_password,
        twikit_cookies_path=settings.twikit_cookies_path,
        twscrape_accounts=settings.get_twscrape_accounts(),
        nitter_instances=settings.get_nitter_instances(),
        bearer_token=settings.twitter_bearer_token,
        debug=debug,
    )

    try:
        tweets = source.fetch()
    except Exception as e:
        if tracer:
            tracer.end_step("FAIL", f"Exception: {e}")
            tracer.print_report()
        raise

    if not tweets:
        msg = (
            f"No tweets found for topics {topics or 'defaults'} "
            f"in the last {settings.twitter_lookback_hours} hours."
        )
        logger.info(msg)
        if tracer:
            tracer.end_step("OK", msg)
            tracer.print_report()
        return

    if tracer:
        tracer.end_step("OK", f"Fetched {len(tweets)} tweets")

    # ─── Step 2: Run Twitter Agent (LLM) ───────────────────────────
    llm_config = settings.get_llm_config()
    if tracer:
        tracer.start_step(
            "2. TWITTER AGENT",
            f"Provider={settings.llm_provider.value}, "
            f"Model={llm_config['model']}, "
            f"Tweets={len(tweets)}, "
            f"FinalTop={settings.twitter_final_top}",
        )

    logger.info(f"Step 2/5: Running Twitter agent on {len(tweets)} tweets...")
    llm = OpenAICompatibleClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config["model"],
        debug=debug,
    )

    actual_topics = source.get_topics()

    try:
        briefing = run_twitter_agent(
            llm=llm,
            tweets=tweets,
            topics=actual_topics,
            max_turns=settings.max_agent_turns,
            max_preview_chars=settings.max_email_preview_chars,
            debug=debug,
        )
    except Exception as e:
        if tracer:
            tracer.end_step("FAIL", f"Exception: {e}")
            tracer.print_report()
        raise

    if tracer:
        tracer.end_step(
            "OK",
            f"Briefing: top10={len(briefing.top10)}, "
            f"keywords={len(briefing.keywords)}",
        )

    # ─── Step 3: Render & Save H5 Page ────────────────────────────
    if tracer:
        tracer.start_step("3. RENDER H5 PAGE")

    logger.info("Step 3/5: Rendering full H5 page...")

    # Generate H5 page
    h5_content = render_twitter_h5_page(briefing)

    # Save to output directory
    output_dir = Path(settings.twitter_h5_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    h5_filename = f"x-tech-briefing-{briefing.date}.html"
    h5_path = output_dir / h5_filename
    h5_path.write_text(h5_content, encoding="utf-8")

    # Determine the URL for the H5 page
    if settings.twitter_h5_base_url:
        h5_url = f"{settings.twitter_h5_base_url.rstrip('/')}/{h5_filename}"
    else:
        h5_url = f"file://{h5_path.absolute()}"

    logger.info(f"H5 page saved: {h5_path.absolute()}")
    logger.info(f"H5 URL: {h5_url}")

    if tracer:
        tracer.end_step(
            "OK",
            f"H5={len(h5_content)} chars, saved to {h5_path}",
        )

    # ─── Step 4: Render Email Digest ──────────────────────────────
    if tracer:
        tracer.start_step("4. RENDER EMAIL DIGEST")

    logger.info("Step 4/5: Rendering email digest...")
    email_html = render_twitter_email_digest(briefing, h5_url=h5_url)
    email_text = render_twitter_briefing_text(briefing, h5_url=h5_url)

    if tracer:
        tracer.end_step(
            "OK",
            f"EmailHTML={len(email_html)} chars, Text={len(email_text)} chars",
        )
        if debug:
            logger.debug(f"[TRACE] Text preview:\n{email_text[:500]}")

    # ─── Step 5: Send Email ────────────────────────────────────────
    subject = f"🔥 X 技术热点 · {briefing.date}"
    if tracer:
        tracer.start_step(
            "5. SEND EMAIL",
            f"To={settings.gmail_address}, Subject={subject}",
        )

    logger.info("Step 5/5: Sending Twitter digest email...")
    sink = EmailSink(
        address=settings.gmail_address,
        app_password=settings.gmail_app_password,
        debug=debug,
    )

    try:
        sink.send_raw(
            subject=subject,
            html_content=email_html,
            text_content=email_text,
        )
    except Exception as e:
        if tracer:
            tracer.end_step("FAIL", f"Exception: {e}")
            tracer.print_report()
        raise

    if tracer:
        tracer.end_step("OK", "Email sent successfully")

    logger.info("✅ X Tech briefing sent successfully!")
    logger.info(f"📄 Full briefing: {h5_url}")

    if tracer:
        tracer.print_report()


def run_pipeline(settings: Settings) -> None:
    """Run the full pipeline: fetch → agent → summarize → send."""
    from src.agent import run_agent
    from src.llm.openai_compatible import OpenAICompatibleClient
    from src.sources.gmail import GmailSource
    from src.sinks.email import EmailSink
    from src.summarizer import render_briefing_html, render_briefing_text

    debug = settings.debug
    tracer = PipelineTracer() if debug else None

    # ─── Step 1: Fetch Emails ───────────────────────────────────────
    if tracer:
        tracer.start_step(
            "1. FETCH EMAILS",
            f"Label='{settings.gmail_label}', Lookback={settings.lookback_hours}h, "
            f"Address={settings.gmail_address[:3]}***@{settings.gmail_address.split('@')[-1] if '@' in settings.gmail_address else '???'}"
        )

    logger.info("Step 1/4: Fetching emails...")
    source = GmailSource(
        address=settings.gmail_address,
        app_password=settings.gmail_app_password,
        label=settings.gmail_label,
        lookback_hours=settings.lookback_hours,
        debug=debug,
    )

    try:
        emails = source.fetch()
    except Exception as e:
        if tracer:
            tracer.end_step("FAIL", f"Exception: {e}")
            tracer.print_report()
        raise

    if not emails:
        msg = f"No newsletter emails found in the last {settings.lookback_hours} hours. Skipping."
        logger.info(msg)
        if tracer:
            tracer.end_step("OK", msg)
            tracer.print_report()
        return

    if tracer:
        tracer.end_step("OK", f"Fetched {len(emails)} emails")
        if debug:
            logger.debug("[TRACE] Email list:")
            for i, email in enumerate(emails, 1):
                logger.debug(
                    f"[TRACE]   {i}. [{email.id}] {email.subject} "
                    f"(from: {email.sender}, date: {email.date}, "
                    f"body_len: {len(email.body_text)} chars)"
                )

    # ─── Step 2: Run Agent (LLM) ───────────────────────────────────
    if tracer:
        llm_config = settings.get_llm_config()
        tracer.start_step(
            "2. LLM AGENT",
            f"Provider={settings.llm_provider.value}, "
            f"Model={llm_config['model']}, "
            f"MaxTurns={settings.max_agent_turns}, "
            f"PreviewChars={settings.max_email_preview_chars}"
        )
    else:
        llm_config = settings.get_llm_config()

    logger.info(f"Step 2/4: Running agent on {len(emails)} emails...")
    llm = OpenAICompatibleClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config["model"],
        debug=debug,
    )

    try:
        briefing = run_agent(
            llm=llm,
            emails=emails,
            max_turns=settings.max_agent_turns,
            max_preview_chars=settings.max_email_preview_chars,
            debug=debug,
        )
    except Exception as e:
        if tracer:
            tracer.end_step("FAIL", f"Exception: {e}")
            tracer.print_report()
        raise

    if tracer:
        tracer.end_step(
            "OK",
            f"Briefing generated: top3={len(briefing.top3)}, "
            f"others={len(briefing.others)}, keywords={len(briefing.keywords)}"
        )

    # ─── Step 3: Render ─────────────────────────────────────────────
    if tracer:
        tracer.start_step("3. RENDER BRIEFING")

    logger.info("Step 3/4: Rendering briefing...")
    html_content = render_briefing_html(briefing)
    text_content = render_briefing_text(briefing)

    if tracer:
        tracer.end_step(
            "OK",
            f"HTML={len(html_content)} chars, Text={len(text_content)} chars"
        )
        if debug:
            logger.debug(f"[TRACE] Text briefing preview:\n{text_content[:500]}")

    # ─── Step 4: Send Email ─────────────────────────────────────────
    if tracer:
        tracer.start_step(
            "4. SEND EMAIL",
            f"To={settings.gmail_address}, Subject=📬 每日简报 · {briefing.date}"
        )

    logger.info("Step 4/4: Sending briefing email...")
    sink = EmailSink(
        address=settings.gmail_address,
        app_password=settings.gmail_app_password,
        debug=debug,
    )

    try:
        sink.send(briefing, html_content, text_content)
    except Exception as e:
        if tracer:
            tracer.end_step("FAIL", f"Exception: {e}")
            tracer.print_report()
        raise

    if tracer:
        tracer.end_step("OK", "Email sent successfully")

    logger.info("✅ Daily briefing sent successfully!")

    # ─── Pipeline Report ────────────────────────────────────────────
    if tracer:
        tracer.print_report()


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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (full pipeline tracing)",
    )
    parser.add_argument(
        "--twitter",
        action="store_true",
        help="Run X/Twitter tech hotspot pipeline (instead of email briefing)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all enabled pipelines (email + twitter)",
    )
    args = parser.parse_args()

    # Determine debug mode from CLI flag or env var
    debug_from_cli = args.debug

    if args.demo:
        setup_logging(debug=False)
        logger.info("Running in DEMO mode...")
        run_demo()
        return

    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        setup_logging(debug=True)
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file or environment variables.")
        logger.error("Run with --demo flag to see a sample output without config.")
        sys.exit(1)

    # CLI --debug flag overrides env var
    if debug_from_cli:
        settings.debug = True

    setup_logging(debug=settings.debug)

    if settings.debug:
        logger.info("[DEBUG] Configuration loaded:")
        logger.info(f"[DEBUG]   GMAIL_ADDRESS: {settings.gmail_address[:3]}***")
        logger.info(f"[DEBUG]   GMAIL_LABEL: {settings.gmail_label}")
        logger.info(f"[DEBUG]   LOOKBACK_HOURS: {settings.lookback_hours}")
        logger.info(f"[DEBUG]   LLM_PROVIDER: {settings.llm_provider.value}")
        llm_cfg = settings.get_llm_config()
        logger.info(f"[DEBUG]   LLM_MODEL: {llm_cfg['model']}")
        logger.info(f"[DEBUG]   LLM_BASE_URL: {llm_cfg['base_url']}")
        logger.info(f"[DEBUG]   MAX_AGENT_TURNS: {settings.max_agent_turns}")
        logger.info(f"[DEBUG]   MAX_PREVIEW_CHARS: {settings.max_email_preview_chars}")
        if settings.twitter_enabled or args.twitter:
            logger.info(f"[DEBUG]   TWITTER_ENABLED: {settings.twitter_enabled}")
            logger.info(f"[DEBUG]   TWITTER_TOPICS: {settings.get_twitter_topics() or 'defaults'}")
            logger.info(f"[DEBUG]   TWITTER_LOOKBACK: {settings.twitter_lookback_hours}h")

    # Determine which pipelines to run
    run_email = True
    run_x = args.twitter or (args.all and settings.twitter_enabled)

    if args.twitter and not args.all:
        # --twitter alone means ONLY run twitter pipeline
        run_email = False
        run_x = True

    # Run email pipeline
    if run_email and not args.twitter:
        # Validate email settings
        if not settings.gmail_address or not settings.gmail_app_password:
            logger.error("GMAIL_ADDRESS and GMAIL_APP_PASSWORD are required.")
            logger.error("See .env.example for configuration template.")
            sys.exit(1)

        llm_config = settings.get_llm_config()
        if not llm_config["api_key"]:
            logger.error(f"API key for provider '{settings.llm_provider.value}' is not set.")
            sys.exit(1)

        run_pipeline(settings)

    # Run Twitter pipeline
    if run_x:
        # Validate minimal config for twitter
        if not settings.gmail_address or not settings.gmail_app_password:
            logger.error("GMAIL_ADDRESS and GMAIL_APP_PASSWORD are required to send the briefing.")
            sys.exit(1)

        llm_config = settings.get_llm_config()
        if not llm_config["api_key"]:
            logger.error(f"API key for provider '{settings.llm_provider.value}' is not set.")
            sys.exit(1)

        # Check if at least one twitter scraper is configured
        has_scraper = (
            settings.twikit_username
            or settings.twikit_cookies_path
            or settings.twscrape_accounts
            or settings.nitter_instances
            or settings.twitter_bearer_token
        )
        if not has_scraper:
            logger.error(
                "No Twitter scraper credentials configured. "
                "You need at least one of:\n"
                "  - TWIKIT_USERNAME + TWIKIT_PASSWORD + TWIKIT_EMAIL (recommended, free)\n"
                "  - A cookies file at .twikit_cookies.json (from previous login)\n"
                "  - TWITTER_BEARER_TOKEN (paid per-use since 2026)\n"
                "  - TWSCRAPE_ACCOUNTS (needs Twitter account credentials)\n"
                "Please configure twikit credentials in your .env file."
            )
            sys.exit(1)

        run_twitter_pipeline(settings)


if __name__ == "__main__":
    cli()
