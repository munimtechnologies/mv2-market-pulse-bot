# MV2 Market Pulse bot

An automated forecasting bot for the Metaculus
[Market Pulse Challenge 26Q4](https://www.metaculus.com/tournament/market-pulse-26q4/) ($7,500 prize pool, bots
eligible, ends Dec 31, 2026). That tournament asks about markets: relative returns, VIX peaks, Treasury yields,
company revenue and EPS. The bot is run by **MV2 of [Munim, Inc.](https://munimtech.com)**. The code was written with
AI agents working in MV2's name, and the bot forecasts with LLMs.

MV2's entry in the FutureEval bot tournament and MiniBench is a separate bot, `munimtechnologies/mv2-forecaster`. Both post from
**one** Metaculus bot account, which is Munim's single entry. This repo forecasts only in Market Pulse.

Its forecasts are public research on a forecasting platform. They are not investment advice.

## How it works

- It is built on the open-source `FallTemplateBot2026` from Metaculus's
  [forecasting-tools](https://github.com/Metaculus/forecasting-tools) (MIT). For each question it does a news research
  step, then makes 5 independent forecasts and combines them. The forecast is posted with its reasoning as a comment.
- **Market data.** The research step also gets recent levels and base rates from official free sources when a
  question mentions them (`market_data.py`, `sec_filings.py`, `vix_window.py`):
  - VIX: [Cboe's VIX history](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv). It gives
    the last close, the recent highs, the 1-year range, and the distribution of the highest intraday high over the
    question's horizon, scaled to today's close. A VIX question usually asks about a two-week window; when the window
    dates can be read from the question, the horizon is the number of trading days to the end of that window,
    otherwise it falls back to 10 trading days. Trading days skip weekends and the NYSE full-day holidays for
    2026-2028 (from [nyse.com](https://www.nyse.com/markets/hours-calendars)), so a window that holds Thanksgiving or
    Christmas gets the right horizon. Market Pulse asks VIX questions as a group with one subquestion per
    two-week period. Each subquestion's period label (e.g. "Oct 19 – Oct 30") is read first, so the shared text that
    lists every period does not pick the wrong one.
  - Treasury yields: the
    [U.S. Treasury par yield curve](https://home.treasury.gov/resource-center/data-chart-center/interest-rates). It
    gives 3M/2Y/10Y/30Y with 5- and 20-day changes, and the distribution of 10-day moves in the 10Y.
  - Company revenue and EPS: [SEC EDGAR's XBRL API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
    For a revenue/EPS question that names a company (a ticker in parentheses, "NASDAQ: XYZ", or a common name such
    as NVIDIA or Apple), it gives the last 8 fiscal quarters of reported revenue (with year-over-year growth) and
    GAAP diluted EPS. A fourth quarter that is only filed inside the annual report is derived as the year minus the
    first nine months, and is marked as derived. The prompt notes that questions may resolve on adjusted figures.
  - If a source is down, the bot goes on without it. Requests identify MV2 of Munim, Inc. with a contact email, as the
    SEC asks.
- **No human in the loop.** GitHub Actions posts every forecast on a schedule. Nobody reviews or edits a forecast on
  an open tournament question.
- Every 20 minutes it forecasts new questions. Twice a day (05:10 and 17:10 UTC) it re-forecasts questions that will
  be scored within the next 13 hours, so the forecast that counts uses fresh data. The scoring moment is Metaculus's
  own `spot_scoring_time` from the question's API data. If that is missing, it uses the earlier of the
  community-prediction reveal and the close (`mv2_config.scoring_time`).
- Models come from repository variables, so they can change without a code change. If no variables are set, it uses
  forecasting-tools' defaults for whichever keys are present.

## Setup (repository owner)

1. **Workflows.** Copy `ci/forecast.yml` and `ci/test.yml` to `.github/workflows/forecast.yml` and
   `.github/workflows/test.yml`. (The tool that publishes this repo may not write to `.github/workflows/`. In the
   GitHub web UI, use *Add file → Create new file*, type the path, and paste the contents.)
2. Use the same Metaculus **bot account** as `mv2-forecaster`. It is created from a human account under Settings → *My
   forecasting bots*, and its token comes from <https://www.metaculus.com/futureeval/participate/>. The participation
   form there offers free LLM credits (as an OpenRouter key) and AskNews access.
3. In this repo, open *Settings → Secrets and variables → Actions* and add these secrets:
   - `METACULUS_TOKEN` (required). On its own, it uses the Metaculus model proxy.
   - `OPENROUTER_API_KEY` (the free credits).
   - Optional: `ASKNEWS_CLIENT_ID` / `ASKNEWS_SECRET`, `EXA_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
4. Optional *variables* (not secrets):
   - `MV2_DEFAULT_MODEL`: the forecasting model as a litellm name, e.g. `openrouter/<provider>/<model>` with an id
     from <https://openrouter.ai/models>.
   - `MV2_RESEARCHER`, e.g. `asknews/news-summaries`.
   - `MV2_SUMMARIZER`, `MV2_PARSER`.
   - `MV2_REFRESH_HOURS` (default 13).
   - `MV2_MARKET_PULSE_ID`, for the next quarter's tournament.
5. Open *Actions → Forecast → Run workflow* and choose `test`. The bot's forecasts should appear in the unscored
   [bot-testing-area](https://www.metaculus.com/tournament/bot-testing-area/). After that, the schedule runs on its own.
   Until `METACULUS_TOKEN` is set, scheduled runs do nothing and exit.

## Run locally

```
pip install -r requirements.txt
cp .env.example .env   # fill it in; never commit it
python main.py --mode test --no-publish
python -m unittest -v test_mv2_config test_market_data test_sec_filings test_vix_window
```

## Rules it follows

- Munim enters Market Pulse once, as this bot account. Nobody at Munim also enters as a human.
- It uses public information only, and testing happens only in the bot-testing-area.
- The code is public, so Metaculus can inspect it.
- Data sources are official public ones whose terms allow automated use. FRED and Yahoo Finance are deliberately not
  used, because their terms limit automated or commercial use.

Apache-2.0 licensed. Contact: munimversion2@gmail.com (MV2 of Munim, Inc.). A person at Munim, Inc. owns the Metaculus
account.
