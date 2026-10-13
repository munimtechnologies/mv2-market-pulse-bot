"""Market context for Market Pulse questions, from official free sources (stdlib only).

- VIX: Cboe's daily VIX history CSV (DATE,OPEN,HIGH,LOW,CLOSE).
- Treasury yields: the U.S. Treasury's daily par yield curve CSV (newest row first).

Each fetch fails soft: any error gives an empty section, and the bot falls back to its news research.
The output is base rates and recent levels for the forecasting prompt, not a forecast or advice.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import urllib.request
from datetime import date, datetime

logger = logging.getLogger(__name__)

USER_AGENT = "mv2-forecast-bot/0.1 (MV2 of Munim, Inc., an AI; munimversion2@gmail.com)"
VIX_URL = "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
    "{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)

VIX_PATTERN = re.compile(r"\bVIX\b|volatility index", re.IGNORECASE)
YIELD_PATTERN = re.compile(r"treasury|\byields?\b|\bT-?bills?\b|\bT-?notes?\b", re.IGNORECASE)

PERCENTILES = (5, 10, 25, 50, 75, 90, 95)


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (0-100) of a non-empty list."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct / 100.0
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _to_float(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "", "N/A") else None
    except ValueError:
        return None


def _to_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_vix_csv(text: str) -> list[dict]:
    """Rows sorted oldest first: {date, open, high, low, close}. Malformed rows are skipped."""
    rows = []
    for record in csv.DictReader(io.StringIO(text)):
        record = {(k or "").strip().lstrip("﻿").upper(): v for k, v in record.items()}
        day = _to_date(record.get("DATE") or "")
        high, close = _to_float(record.get("HIGH")), _to_float(record.get("CLOSE"))
        if day is None or high is None or close is None:
            continue
        rows.append({"date": day, "high": high, "close": close})
    rows.sort(key=lambda r: r["date"])
    return rows


def forward_max_ratios(rows: list[dict], horizon: int) -> list[float]:
    """For each start day: max intraday high over the next `horizon` trading days divided by that day's close."""
    ratios = []
    for i in range(len(rows) - horizon):
        start = rows[i]["close"]
        if start > 0:
            ratios.append(max(r["high"] for r in rows[i + 1 : i + 1 + horizon]) / start)
    return ratios


def summarize_vix(rows: list[dict], horizon: int = 10, lookback_days: int = 1260) -> str:
    if len(rows) < horizon + 30:
        return ""
    last = rows[-1]
    recent = rows[-lookback_days:]
    closes_1y = [r["close"] for r in rows[-252:]]
    ratios = forward_max_ratios(recent, horizon)
    lines = [
        f"VIX (Cboe daily history, last row {last['date'].isoformat()}): close {last['close']:.2f}.",
        "Highest intraday high over the last 5 / 10 / 20 trading days: "
        + " / ".join(f"{max(r['high'] for r in rows[-n:]):.2f}" for n in (5, 10, 20))
        + ".",
        f"Last 252 trading days, close: min {min(closes_1y):.2f}, median {percentile(closes_1y, 50):.2f}, "
        f"max {max(closes_1y):.2f}.",
    ]
    if ratios:
        implied = ", ".join(
            f"p{p} {last['close'] * percentile(ratios, p):.2f}" for p in PERCENTILES
        )
        lines.append(
            f"Base rate from the last {len(recent)} trading days: the highest intraday high over the next "
            f"{horizon} trading days, as a multiple of the starting close, scaled to today's close: {implied}."
        )
    return "\n".join(lines)


def parse_treasury_csv(text: str) -> list[dict]:
    """Rows sorted oldest first: {date, <column>: float|None}. Column names as Treasury gives them ("10 Yr")."""
    rows = []
    for record in csv.DictReader(io.StringIO(text)):
        record = {(k or "").strip().lstrip("﻿"): v for k, v in record.items()}
        day = _to_date(record.pop("Date", "") or "")
        if day is None:
            continue
        row = {"date": day}
        row.update({k: _to_float(v) for k, v in record.items() if k})
        rows.append(row)
    rows.sort(key=lambda r: r["date"])
    return rows


def summarize_yields(rows: list[dict], tenors: tuple[str, ...] = ("3 Mo", "2 Yr", "10 Yr", "30 Yr"), horizon: int = 10) -> str:
    if len(rows) < 25:
        return ""
    last = rows[-1]
    parts = []
    for tenor in tenors:
        series = [r.get(tenor) for r in rows]
        if series[-1] is None:
            continue
        text = f"{tenor} {series[-1]:.2f}%"
        for lag in (5, 20):
            if len(series) > lag and series[-1 - lag] is not None:
                text += f", {(series[-1] - series[-1 - lag]) * 100:+.0f} bp vs {lag} trading days ago"
        parts.append(text)
    if not parts:
        return ""
    lines = [f"U.S. Treasury par yields (treasury.gov, last row {last['date'].isoformat()}): " + "; ".join(parts) + "."]
    ten = [r.get("10 Yr") for r in rows]
    changes = [
        (ten[i + horizon] - ten[i]) * 100
        for i in range(len(ten) - horizon)
        if ten[i] is not None and ten[i + horizon] is not None
    ]
    if len(changes) >= 20:
        lines.append(
            f"Base rate from the last {len(ten)} trading days: 10 Yr change over {horizon} trading days, in bp: "
            + ", ".join(f"p{p} {percentile(changes, p):+.0f}" for p in PERCENTILES)
            + "."
        )
    return "\n".join(lines)


def _fetch(url: str, timeout: float = 20.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def vix_context() -> str:
    try:
        return summarize_vix(parse_vix_csv(_fetch(VIX_URL)))
    except Exception as error:
        logger.warning("VIX data unavailable: %s", error)
        return ""


def treasury_context(today: date | None = None) -> str:
    year = (today or date.today()).year
    rows: list[dict] = []
    for y in (year - 1, year):
        try:
            rows += parse_treasury_csv(_fetch(TREASURY_URL.format(year=y)))
        except Exception as error:
            logger.warning("Treasury data for %s unavailable: %s", y, error)
    rows.sort(key=lambda r: r["date"])
    return summarize_yields(rows)


def market_context(question_text: str) -> str:
    """Data sections relevant to the question text, or "" if none apply or the sources are down."""
    sections = []
    if VIX_PATTERN.search(question_text):
        sections.append(vix_context())
    if YIELD_PATTERN.search(question_text):
        sections.append(treasury_context())
    sections = [s for s in sections if s]
    if not sections:
        return ""
    return "Market data (official sources, fetched just now):\n" + "\n\n".join(sections)
