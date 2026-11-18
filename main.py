"""MV2's forecasting bot for Metaculus Market Pulse.

Run by MV2 of Munim, Inc. This bot is fully automated: no human looks at or edits a forecast before
it is posted. It uses the open-source FallTemplateBot2026 from Metaculus's forecasting-tools (MIT),
adds VIX, implied-volatility and Treasury-yield base rates and SEC-reported revenue/EPS history to the
research for questions that mention them, takes model choice from environment variables, refreshes
forecasts shortly before each question is scored, and posts its reasoning with every link removed.

If the news-research step fails (for example, no search-capable model is reachable), the bot still
forecasts from the official market data above instead of failing the whole question. Each run ends
with one summary line that names the root cause of any failed question, with secrets masked.

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

NO_NEWS_NOTE = "No news research was available for this run; the forecast rests on the market data above, if any."


def build_bot(publish: bool):
    from forecasting_tools import FallTemplateBot2026, GeneralLlm

    class MarketPulseBot(FallTemplateBot2026):
        mv2_research_fallbacks = 0

        async def run_research(self, question):
            try:
                research = await super().run_research(question)
            except Exception as exc:  # a failed search must not sink the forecast
                type(self).mv2_research_fallbacks += 1
                cause = mv2_config.root_cause(exc)
                logger.warning(
                    "News research failed (%s: %s); forecasting on market data only",
                    type(cause).__name__,
                    mv2_config.redact(" ".join(str(cause).split()))[:200],
                )
                research = ""
            context = await asyncio.to_thread(market_data.market_context, mv2_config.research_text(question))
            if context and research:
                return f"{context}\n\n{research}"
            return context or research or NO_NEWS_NOTE

        def _create_unified_explanation(self, *args, **kwargs):
            # The explanation is posted as a Metaculus comment; links in comments trip its spam filter.
            return mv2_config.strip_links(super()._create_unified_explanation(*args, **kwargs))

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

    bot = MarketPulseBot(
        research_reports_per_question=1,
        predictions_per_research_report=5,
        use_research_summary_to_forecast=False,
        publish_reports_to_metaculus=publish,
        folder_to_save_reports_to=None,
        skip_previously_forecasted_questions=True,
        extra_metadata_in_explanation=True,
        llms=llms,
    )
    return bot, MarketPulseBot


def run(mode: str, publish: bool) -> int:
    from forecasting_tools import MetaculusClient

    missing = mv2_config.missing_secrets()
    if missing:
        print(f"Not forecasting: missing {', '.join(missing)}. See README 'Setup'.")
        return 0

    bot, bot_cls = build_bot(publish)
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
    print(mv2_config.run_summary(mode, reports, publish, research_fallbacks=bot_cls.mv2_research_fallbacks))
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
