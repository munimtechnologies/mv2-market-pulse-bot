"""MV2's forecasting bot for Metaculus Market Pulse.

MV2 is an AI person at Munim, Inc. This bot is fully automated: no human looks at or edits a
forecast before it is posted. It uses the open-source FallTemplateBot2026 from Metaculus's
forecasting-tools (MIT), adds VIX and Treasury-yield base rates from official sources to the
research for questions that mention them, takes model choice from repo variables, and refreshes
forecasts shortly before each question is scored.

Modes:
  tournament  new Market Pulse questions (every 20 minutes)
  refresh     Market Pulse questions scored within the next MV2_REFRESH_HOURS (twice a day)
  test        all questions in the unscored bot-testing-area
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

import market_data
import mv2_config

try:
    import dotenv

    dotenv.load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("mv2")


def build_bot(publish: bool):
    from forecasting_tools import FallTemplateBot2026, GeneralLlm

    class MarketPulseBot(FallTemplateBot2026):
        async def run_research(self, question):
            research = await super().run_research(question)
            context = await asyncio.to_thread(market_data.market_context, mv2_config.research_text(question))
            return f"{context}\n\n{research}" if context else research

    llms = None
    overrides = mv2_config.llm_overrides()
    if overrides:
        llms = dict(FallTemplateBot2026._llm_config_defaults())
        llms.update(overrides)
        if "default" in overrides:
            llms["default"] = GeneralLlm(
                model=overrides["default"], temperature=0.3, timeout=120, allowed_tries=2
            )
        logger.info("Model overrides: %s", overrides)

    return MarketPulseBot(
        research_reports_per_question=1,
        predictions_per_research_report=5,
        use_research_summary_to_forecast=False,
        publish_reports_to_metaculus=publish,
        folder_to_save_reports_to=None,
        skip_previously_forecasted_questions=True,
        extra_metadata_in_explanation=True,
        llms=llms,
    )


def run(mode: str, publish: bool) -> int:
    from forecasting_tools import MetaculusClient

    missing = mv2_config.missing_secrets()
    if missing:
        print(f"Not forecasting: missing {', '.join(missing)}. See README 'Setup'.")
        return 0

    bot = build_bot(publish)
    tournament = mv2_config.market_pulse_id(client_cls=MetaculusClient)
    reports = []

    if mode == "tournament":
        logger.info("Forecasting new questions in %s", tournament)
        reports += asyncio.run(bot.forecast_on_tournament(tournament, return_exceptions=True))
    elif mode == "refresh":
        window = float(os.getenv("MV2_REFRESH_HOURS") or 13)
        questions = MetaculusClient().get_all_open_questions_from_tournament(tournament)
        due = mv2_config.due_for_refresh(questions, datetime.now(timezone.utc), window_hours=window)
        logger.info("%s: %d open, %d due for refresh", tournament, len(questions), len(due))
        if due:
            bot.skip_previously_forecasted_questions = False
            reports += asyncio.run(bot.forecast_questions(due, return_exceptions=True))
    elif mode == "test":
        bot.skip_previously_forecasted_questions = False
        reports += asyncio.run(bot.forecast_on_tournament("bot-testing-area", return_exceptions=True))

    if reports:
        bot.log_report_summary(reports, raise_errors=False)
    errors = sum(1 for r in reports if isinstance(r, BaseException))
    print(f"MV2 forecast run ({mode}): {len(reports) - errors} forecasts, {errors} errors, publish={publish}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="MV2's Metaculus Market Pulse bot")
    parser.add_argument("--mode", choices=["tournament", "refresh", "test"], default="tournament")
    parser.add_argument("--no-publish", action="store_true", help="run without posting forecasts")
    args = parser.parse_args(argv)
    return run(args.mode, publish=not args.no_publish)


if __name__ == "__main__":
    sys.exit(main())
