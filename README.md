# MV2 Market Pulse bot

An automated forecasting bot for the Metaculus
[Market Pulse Challenge 26Q4](https://www.metaculus.com/tournament/market-pulse-26q4/) ($7,500 prize pool, bots
eligible, ends Dec 31, 2026). That tournament asks about markets: relative returns, VIX peaks, Treasury yields,
company revenue and EPS. The bot is run by **MV2 of [Munim, Inc.](https://munimtech.com)**. The code was written with
AI agents working in MV2's name, and the bot forecasts with LLMs.

MV2's entry in the FutureEval bot tournament and MiniBench is a separate bot, `munimtechnologies/mv2-forecaster`. Both
post from **one** Metaculus bot account, which is Munim's single entry. This repo forecasts only in Market Pulse.

Its forecasts are public research on a forecasting platform. They are not investment advice.

## How it works

- It is built on the open-source `FallTemplateBot2026` from Metaculus's
  [forecasting-tools](https://github.com/Metaculus/forecasting-tools) (MIT). For each question it does a news research
  step, then makes 5 independent forecasts and combines them. The forecast is posted with its reasoning as a comment.
- **Link-free comments.** The research step cites its sources as URLs, and links in Metaculus comments can trip the
  site's spam filter. Before a comment is posted, `mv2_config.strip_links` removes every link: a markdown link keeps
  its text, and a bare URL or domain becomes the site's short name (`https://www.reuters.com/...` becomes `reuters`).
- **Market data.** The research step also gets recent levels and base rates from official free sources when a
  question mentions them (`market_data.py`, `pair_vol.py`, `sec_filings.py`, `vix_window.py`):
  - VIX: [Cboe's VIX history](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv). It gives
    the last close, the recent highs, the 1-year range, and the distribution of the highest intraday high over the
    question's horizon, scaled to today's close. A VIX question usually asks about a two-week window; when the window
    dates can be read from the question, the horizon is the number of trading days to the end of that window,
    otherwise it falls back to 10 trading days. Trading days skip weekends and the NYSE full-day holidays for
    2026-2028 (from [nyse.com](https://www.nyse.com/markets/hours-calendars)), so a window that holds Thanksgiving or
    Christmas gets the right horizon. Market Pulse asks VIX questions as a group with one subquestion per
    two-week period. Each subquestion's period label (e.g. "Oct 19 – Oct 30") is read first, so the shared text that
    lists every period does not pick the wrong one.
  - Pair questions: Market Pulse also asks for the difference between two markets' returns over a two-week window,
    in percentage points (e.g. "NQ − ES", "Gold − ES", crude oil vs ES). For a question that names two of these legs,
    the bot reads Cboe's 30-day implied volatility index for each one: VIX (S&P 500), VXN (Nasdaq-100), GVZ (gold) and
    OVX (crude oil), from the same Cboe daily history files. It gives each index's latest level and 1-year median,
    the one-standard-deviation move of each leg over the window's trading days, and the spread's standard deviation
    and 10th-90th percentile range for assumed correlations of 0, 0.5 and 0.9 between the two returns. The text says
    that implied vol usually runs above the volatility that follows, and that GVZ and OVX come from ETF options.
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
- **A failed news search does not sink a forecast** (v0.4.1). With no search key set, forecasting-tools picks a
  default search model (for a Metaculus token alone, the Metaculus proxy's search model). If that call fails, the
  question used to fail outright. Now the bot logs a warning and forecasts from the market data above, and the run's
  summary counts these as `research_fallbacks`.
- **Every run says why it failed** (v0.4.1). The last line of each run keeps its old start,
  `MV2 forecast run (mode): N forecasts, M errors, publish=...`, and then names the root cause of the failed
  questions (`mv2_config.run_summary`), for example `| PermissionError x11: 403 Forbidden`. Anything that looks like a
  token or key is masked before it is printed.
- **No human in the loop.** A scheduler posts every forecast. Nobody reviews or edits a forecast on an open tournament
  question.
- Every 20 minutes it forecasts new questions. Twice a day (05:10 and 17:10 UTC) it re-forecasts questions that will
  be scored within the next 13 hours, so the forecast that counts uses fresh data. The scoring moment is Metaculus's
  own `spot_scoring_time` from the question's API data. If that is missing, it uses the earlier of the
  community-prediction reveal and the close (`mv2_config.scoring_time`).
- Models come from environment variables, so they can change without a code change. If none are set, it uses
  forecasting-tools' defaults for whichever keys are present.

## Running it

It runs anywhere Python 3.11+ can reach metaculus.com: on Munim's own machine under a scheduler, or on GitHub Actions.
Run the same three commands on the same schedule either way:

```
python main.py --mode tournament   # every 20 minutes
python main.py --mode refresh      # 05:10 and 17:10 UTC
python main.py --mode test         # once, before the first real run: posts only in the bot-testing-area
```

Environment (secrets come from the environment only, never from a file in this repo):

- `METACULUS_TOKEN` (required): the token of the one Metaculus bot account shared with `mv2-forecaster`.
- One LLM route: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `OPENROUTER_API_KEY` (litellm also honours a base-URL
  variable for a self-hosted proxy). `METACULUS_TOKEN` alone uses the Metaculus model proxy where it is offered.
- Optional: `ASKNEWS_CLIENT_ID` / `ASKNEWS_SECRET`, `EXA_API_KEY`.
- Optional variables: `MV2_DEFAULT_MODEL` (a litellm model name), `MV2_RESEARCHER` (e.g. `asknews/news-summaries`,
  or `no_research` to forecast on market data alone), `MV2_SUMMARIZER`, `MV2_PARSER`, `MV2_REFRESH_HOURS`
  (default 13), `MV2_MARKET_PULSE_ID` (next quarter's tournament; 26Q4 is `market-pulse-26q4`, id 33131).

Until `METACULUS_TOKEN` is set, every run does nothing and exits.

**On GitHub Actions:** copy `ci/forecast.yml` and `ci/test.yml` to `.github/workflows/` (the tool that publishes this
repo does not write to `.github/workflows/`; in the web UI use *Add file → Create new file*), then add the secrets
under *Settings → Secrets and variables → Actions* and the optional ones as variables.

## Run locally

```
pip install -r requirements.txt
cp .env.example .env   # fill it in; never commit it
python main.py --mode test --no-publish
python -m unittest discover -v -p "test_*.py"
```

## Rules it follows

- Munim enters Market Pulse once, as this bot account. Nobody at Munim also enters as a human.
- It uses public information only, and testing happens only in the bot-testing-area.
- The code is public, so Metaculus can inspect it.
- Comments carry no links.
- Data sources are official public ones whose terms allow automated use. FRED and Yahoo Finance are deliberately not
  used, because their terms limit automated or commercial use.

Apache-2.0 licensed. Contact: mv2@munimtech.com (MV2 of Munim, Inc.). A person at Munim, Inc. owns the Metaculus
account.
