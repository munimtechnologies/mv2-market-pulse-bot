# MV2 Market Pulse bot

An automated forecasting bot for the Metaculus
[Market Pulse Challenge 26Q4](https://www.metaculus.com/tournament/market-pulse-26q4/) ($7,500 prize pool, bots
eligible, ends Dec 31, 2026). That tournament asks about markets: relative returns, VIX peaks, Treasury yields,
company revenue and EPS. The bot is run by **MV2, an AI person at [Munim, Inc.](https://munimtech.com)**.

MV2's entry in the FutureEval bot tournament and MiniBench is a separate bot, `munimv2/mv2-forecaster`. Both post from
**one** Metaculus bot account, which is Munim's single entry. This repo forecasts only in Market Pulse.

Its forecasts are public research on a forecasting platform. They are not investment advice.

## How it works

- It is built on the open-source `FallTemplateBot2026` from Metaculus's
  [forecasting-tools](https://github.com/Metaculus/forecasting-tools) (MIT). For each question it does a news research
  step, then makes 5 independent forecasts and combines them. The forecast is posted with its reasoning as a comment.
- **Market data.** When a question mentions the VIX or Treasury yields, the research also gets recent levels and base
  rates from official free sources (`market_data.py`):
  - [Cboe's VIX history](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv): the last close,
    the recent highs, the 1-year range, and the distribution of the highest intraday high over the next 10 trading
    days, scaled to today's close.
  - The [U.S. Treasury par yield curve](https://home.treasury.gov/resource-center/data-chart-center/interest-rates):
    3M/2Y/10Y/30Y with 5- and 20-day changes, and the distribution of 10-day moves in the 10Y.
  - If a source is down, the bot goes on without it.
- **No human in the loop.** GitHub Actions posts every forecast on a schedule. Nobody reviews or edits a forecast on
  an open tournament question.
- Every 20 minutes it forecasts new questions. Twice a day (05:10 and 17:10 UTC) it re-forecasts questions that will
  be scored within the next 13 hours, so the forecast that counts uses fresh data. A question is scored at the earlier
  of its close and its community-prediction reveal (`mv2_config.due_for_refresh`).
- Models come from repository variables, so they can change without a code change. If no variables are set, it uses
  forecasting-tools' defaults for whichever keys are present.

## Setup (repository owner)

1. Use the same Metaculus **bot account** as `mv2-forecaster`. It is created from a human account under Settings → *My
   forecasting bots*, and its token comes from <https://www.metaculus.com/futureeval/participate/>. The participation
   form there offers free LLM credits (as an OpenRouter key) and AskNews access.
2. In this repo, open *Settings → Secrets and variables → Actions* and add these secrets:
   - `METACULUS_TOKEN` (required). On its own, it uses the Metaculus model proxy.
   - `OPENROUTER_API_KEY` (the free credits).
   - Optional: `ASKNEWS_CLIENT_ID` / `ASKNEWS_SECRET`, `EXA_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
3. Optional *variables* (not secrets):
   - `MV2_DEFAULT_MODEL`: the forecasting model as a litellm name, e.g. `openrouter/<provider>/<model>` with an id
     from <https://openrouter.ai/models>.
   - `MV2_RESEARCHER`, e.g. `asknews/news-summaries`.
   - `MV2_SUMMARIZER`, `MV2_PARSER`.
   - `MV2_REFRESH_HOURS` (default 13).
   - `MV2_MARKET_PULSE_ID`, for the next quarter's tournament.
4. Open *Actions → Forecast → Run workflow* and choose `test`. The bot's forecasts should appear in the unscored
   [bot-testing-area](https://www.metaculus.com/tournament/bot-testing-area/). After that, the schedule runs on its own.
   Until `METACULUS_TOKEN` is set, scheduled runs do nothing and exit.

## Run locally

```
pip install -r requirements.txt
cp .env.example .env   # fill it in; never commit it
python main.py --mode test --no-publish
python -m unittest -v test_mv2_config test_market_data
```

## Rules it follows

- Munim enters Market Pulse once, as this bot account. Nobody at Munim also enters as a human.
- It uses public information only, and testing happens only in the bot-testing-area.
- The code is public, so Metaculus can inspect it.

MIT licensed. Contact: munimversion2@gmail.com. MV2 is an AI, and a human at Munim, Inc. owns the Metaculus account.
