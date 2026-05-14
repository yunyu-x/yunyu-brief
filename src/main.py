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
