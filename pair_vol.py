"""Implied-volatility context for Market Pulse pair questions (stdlib only).

Market Pulse also asks for the difference between two markets' returns over a two-week window, in percentage points
("NQ − ES", "Gold − ES", crude oil vs ES). Cboe publishes a 30-day implied volatility index for each of those legs:
VIX (S&P 500), VXN (Nasdaq-100), GVZ (gold, from GLD options) and OVX (crude oil, from USO options). This module finds
the legs a question names and turns their latest implied vols into the typical size of the spread over the window,
for a few assumed correlations between the two returns.

Nothing here fetches anything or gives advice; market_data.py does the fetching.
"""

from __future__ import annotations

import csv
import io
import math
import re
import statistics
from datetime import date, datetime

import vix_window

# Leg name -> (Cboe volatility index, pattern naming the leg). Futures tickers are matched in capitals only, so the
# word "es" in other text is not read as the S&P 500.
LEGS = {
    "S&P 500": ("VIX", re.compile(r"\bES\b|(?i:\bS&P\s?500\b)")),
    "Nasdaq-100": ("VXN", re.compile(r"\bNQ\b|(?i:\bNasdaq[\s-]?100\b)")),
    "Gold": ("GVZ", re.compile(r"\bGC\b|(?i:\bgold\b)")),
    "Crude oil": ("OVX", re.compile(r"\bCL\b|(?i:\bcrude\b|\bWTI\b)")),
}

DEFAULT_DAYS = 10
CORRELATIONS = (0.0, 0.5, 0.9)
Z90 = 1.2816  # standard normal 90th percentile


def find_legs(text: str) -> list[str]:
    """Legs named in the text, in order of first mention."""
    found = []
    for name, (_, pattern) in LEGS.items():
        match = pattern.search(text or "")
        if match:
            found.append((match.start(), name))
    return [name for _, name in sorted(found)]


def parse_cboe_csv(text: str, symbol: str) -> list[tuple[date, float]]:
    """(date, close) rows oldest first from a Cboe daily history CSV. Malformed rows are skipped.

    VIX and VXN files have DATE,OPEN,HIGH,LOW,CLOSE; GVZ and OVX files have DATE,<symbol>.
    """
    rows = []
    for record in csv.DictReader(io.StringIO(text)):
        record = {(k or "").strip().lstrip("\ufeff").upper(): v for k, v in record.items()}
        value = record.get("CLOSE") if "CLOSE" in record else record.get(symbol.upper())
        try:
            day = datetime.strptime((record.get("DATE") or "").strip(), "%m/%d/%Y").date()
            close = float(value)
        except (TypeError, ValueError):
            continue
        if close > 0:
            rows.append((day, close))
    rows.sort()
    return rows


def spread_sd(vol_a: float, vol_b: float, corr: float, days: int) -> float:
    """One standard deviation of (return A - return B) over `days` trading days, in percentage points.

    vol_a and vol_b are annualized implied vols in percent (VIX 20 = 20% a year), with 252 trading days a year.
    """
    variance = vol_a**2 + vol_b**2 - 2 * corr * vol_a * vol_b
    return math.sqrt(max(variance, 0.0) * days / 252)


def window_days(window: tuple[date, date] | None) -> int:
    """Trading days in the question window, or DEFAULT_DAYS if there is none (or it holds no trading day)."""
    if window is None:
        return DEFAULT_DAYS
    days = vix_window.trading_days_inclusive(window[0], window[1])
    return days if days >= 1 else DEFAULT_DAYS


def summarize_pair(
    legs: list[str],
    series: dict[str, list[tuple[date, float]]],
    days: int,
    window: tuple[date, date] | None = None,
) -> str:
    """Implied vols of both legs and the spread's typical size over `days` trading days, or "" without data."""
    if len(legs) < 2 or any(not series.get(leg) for leg in legs[:2]):
        return ""
    first, second = legs[0], legs[1]
    vols = {}
    levels = []
    for leg in (first, second):
        rows = series[leg]
        last_day, last = rows[-1]
        vols[leg] = last
        median = statistics.median(close for _, close in rows[-252:])
        levels.append(f"{leg} ({LEGS[leg][0]}) {last:.2f} on {last_day.isoformat()}, 1-year median {median:.2f}")
    lines = ["Implied volatility, 30-day, annualized (Cboe daily history): " + "; ".join(levels) + "."]
    if window is not None:
        lines.append(f"Question window {window[0].isoformat()} to {window[1].isoformat()}: {days} trading days.")
    else:
        lines.append(f"No question window found in the text; using {days} trading days.")
    lines.append(
        f"At these implied vols, one standard deviation of each return over {days} trading days: "
        + ", ".join(f"{leg} {vols[leg] * math.sqrt(days / 252):.2f}%" for leg in (first, second))
        + "."
    )
    bands = []
    for corr in CORRELATIONS:
        sd = spread_sd(vols[first], vols[second], corr, days)
        bands.append(f"corr {corr:.1f}: sd {sd:.2f}, 10th to 90th percentile {-Z90 * sd:+.2f} to {Z90 * sd:+.2f}")
    lines.append(
        f"{first} return minus {second} return, in percentage points, centred on 0 (normal approximation), "
        "by assumed correlation of the two returns: " + "; ".join(bands) + "."
    )
    note = (
        "Implied vol usually runs above the volatility that follows, so these ranges tend to be a little wide; "
        "how closely the two markets have moved together lately decides which correlation row fits best."
    )
    if {"Gold", "Crude oil"} & {first, second}:
        note += " GVZ and OVX come from options on the GLD and USO ETFs, so they stand in for the futures."
    lines.append(note)
    return "\n".join(lines)
