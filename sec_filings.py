"""Quarterly revenue and diluted EPS history from SEC EDGAR's XBRL API (stdlib only).

For Market Pulse questions about a company's reported revenue or EPS. Sources:
- https://www.sec.gov/files/company_tickers.json (ticker -> CIK)
- https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<tag>.json

The SEC asks automated clients to send a User-Agent with a contact and stay under 10 requests a second; a question
needs at most a handful. Each fetch fails soft. The output is reported history for the forecasting prompt, not a
forecast or advice.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import date

logger = logging.getLogger(__name__)

USER_AGENT = "MV2 of Munim, Inc. munimversion2@gmail.com"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
EPS_TAG = "EarningsPerShareDiluted"

EARNINGS_PATTERN = re.compile(
    r"\brevenues?\b|\bEPS\b|earnings per share|\bnet (?:income|sales)\b|\bearnings\b", re.IGNORECASE
)

# Names as questions usually write them (case-sensitive) -> ticker.
NAME_ALIASES = {
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "NVIDIA": "NVDA",
    "Nvidia": "NVDA",
    "Advanced Micro Devices": "AMD",
    "AMD": "AMD",
    "Tesla": "TSLA",
    "Amazon": "AMZN",
    "Alphabet": "GOOGL",
    "Google": "GOOGL",
    "Meta Platforms": "META",
    "Netflix": "NFLX",
    "Broadcom": "AVGO",
    "Oracle": "ORCL",
    "Intel": "INTC",
    "Palantir": "PLTR",
    "Micron": "MU",
    "Qualcomm": "QCOM",
    "Salesforce": "CRM",
    "Adobe": "ADBE",
    "JPMorgan": "JPM",
    "Walmart": "WMT",
    "Costco": "COST",
}
TICKER_PATTERNS = (
    re.compile(r"\((?:(?:NASDAQ|Nasdaq|NYSE)\s*:\s*)?([A-Z]{1,5}(?:\.[A-Z])?)\)"),
    re.compile(r"\b(?:NASDAQ|Nasdaq|NYSE)\s*:\s*([A-Z]{1,5}(?:\.[A-Z])?)\b"),
)
# Parenthesized words that are not the company's ticker even when some fund trades under them.
NOT_TICKERS = {"AI", "CEO", "CFO", "EPS", "ETF", "GAAP", "GDP", "IPO", "SEC", "US", "USA", "USD", "YOY"}
MAX_COMPANIES = 3


def find_tickers(text: str) -> list[str]:
    """Tickers named in the text, in order of first mention: '(NVDA)', 'NASDAQ: NVDA', or a known company name."""
    hits: list[tuple[int, str]] = []
    for pattern in TICKER_PATTERNS:
        hits += [(m.start(), m.group(1)) for m in pattern.finditer(text)]
    for name, ticker in NAME_ALIASES.items():
        hits += [(m.start(), ticker) for m in re.finditer(rf"\b{re.escape(name)}\b", text)]
    tickers: list[str] = []
    for _, ticker in sorted(hits):
        if ticker not in tickers and ticker not in NOT_TICKERS:
            tickers.append(ticker)
    return tickers


def parse_ticker_map(data: dict) -> dict[str, tuple[int, str]]:
    """company_tickers.json -> {TICKER: (cik, title)}."""
    result = {}
    for entry in data.values() if isinstance(data, dict) else []:
        try:
            result[str(entry["ticker"]).upper()] = (int(entry["cik_str"]), str(entry.get("title") or entry["ticker"]))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _iso(text) -> date | None:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def quarterly_values(facts: list[dict]) -> list[dict]:
    """Fiscal-quarter values, oldest first: {end, val, derived}.

    Three-month facts are used as filed (the latest filing wins for restated periods). A fourth quarter that is only
    reported inside the annual figure is derived as fiscal year minus the first nine months, and marked derived.
    """
    quarters: dict[date, tuple[str, float]] = {}
    annual: dict[tuple[date, date], tuple[str, float]] = {}
    nine_months: dict[tuple[date, date], tuple[str, float]] = {}
    for fact in facts:
        start, end, val = _iso(fact.get("start")), _iso(fact.get("end")), fact.get("val")
        if start is None or end is None or not isinstance(val, (int, float)):
            continue
        filed = str(fact.get("filed") or "")
        days = (end - start).days
        if 80 <= days <= 100:
            if end not in quarters or filed >= quarters[end][0]:
                quarters[end] = (filed, float(val))
        elif 350 <= days <= 380:
            if (start, end) not in annual or filed >= annual[(start, end)][0]:
                annual[(start, end)] = (filed, float(val))
        elif 260 <= days <= 285:
            if (start, end) not in nine_months or filed >= nine_months[(start, end)][0]:
                nine_months[(start, end)] = (filed, float(val))

    rows = {end: {"end": end, "val": val, "derived": False} for end, (_, val) in quarters.items()}
    for (start, end), (_, val) in sorted(annual.items()):
        if any(abs((end - q).days) <= 7 for q in rows):
            continue
        firsts = [(e, v) for (s, e), (_, v) in nine_months.items() if s == start and e < end]
        if firsts:
            _, first_val = max(firsts)
            rows[end] = {"end": end, "val": val - first_val, "derived": True}
    return [rows[k] for k in sorted(rows)]


def _year_ago(rows: list[dict], index: int) -> dict | None:
    end = rows[index]["end"]
    for row in rows[:index]:
        if 350 <= (end - row["end"]).days <= 380:
            return row
    return None


def _money(value: float) -> str:
    if abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    return f"${value / 1e6:.1f}M"


def format_series(rows: list[dict], kind: str, count: int = 8) -> str:
    """One line per quarter, newest last, with year-over-year change. kind is 'revenue' or 'eps'."""
    start = max(0, len(rows) - count)
    lines = []
    for i in range(start, len(rows)):
        row = rows[i]
        value = _money(row["val"]) if kind == "revenue" else f"${row['val']:.2f}"
        text = f"  quarter ended {row['end'].isoformat()}: {value}{'*' if row['derived'] else ''}"
        prior = _year_ago(rows, i)
        if prior and prior["val"]:
            if kind == "revenue":
                text += f" (YoY {(row['val'] / prior['val'] - 1) * 100:+.1f}%)"
            else:
                text += f" (a year earlier ${prior['val']:.2f})"
        lines.append(text)
    return "\n".join(lines)


def summarize_company(ticker: str, title: str, revenue: list[dict], eps: list[dict], revenue_tag: str = "") -> str:
    if not revenue and not eps:
        return ""
    lines = [f"{title} ({ticker}), from its SEC 10-Q/10-K XBRL filings (fiscal quarters):"]
    if revenue:
        lines.append(f"Revenue (us-gaap:{revenue_tag or 'revenue'}):")
        lines.append(format_series(revenue, "revenue"))
    if eps:
        lines.append("Diluted EPS, GAAP (us-gaap:EarningsPerShareDiluted):")
        lines.append(format_series(eps, "eps"))
    if any(r["derived"] for r in revenue[-8:] + eps[-8:]):
        lines.append("* fourth quarter derived as fiscal year minus the first nine months (approximate for EPS).")
    return "\n".join(lines)


_cache: dict[str, object] = {}


def _fetch_json(url: str, timeout: float = 20.0):
    if url not in _cache:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            _cache[url] = json.loads(response.read().decode("utf-8"))
    return _cache[url]


def _concept_facts(cik: int, tag: str, unit: str) -> list[dict]:
    try:
        data = _fetch_json(CONCEPT_URL.format(cik=cik, tag=tag))
    except Exception as error:  # 404 when the company never used this tag
        logger.info("SEC %s for CIK %s unavailable: %s", tag, cik, error)
        return []
    facts = (data.get("units") or {}).get(unit) or []
    return [f for f in facts if str(f.get("form") or "").startswith(("10-Q", "10-K"))]


def company_context(ticker: str, cik: int, title: str) -> str:
    best_tag, revenue = "", []
    for tag in REVENUE_TAGS:
        rows = quarterly_values(_concept_facts(cik, tag, "USD"))
        if rows and (not revenue or rows[-1]["end"] > revenue[-1]["end"]):
            best_tag, revenue = tag, rows
    eps = quarterly_values(_concept_facts(cik, EPS_TAG, "USD/shares"))
    return summarize_company(ticker, title, revenue, eps, best_tag)


def earnings_context(question_text: str) -> str:
    """Revenue and EPS history for the companies a revenue/EPS question names, or ""."""
    if not EARNINGS_PATTERN.search(question_text):
        return ""
    tickers = find_tickers(question_text)[:MAX_COMPANIES]
    if not tickers:
        return ""
    try:
        ticker_map = parse_ticker_map(_fetch_json(TICKERS_URL))
    except Exception as error:
        logger.warning("SEC ticker list unavailable: %s", error)
        return ""
    sections = []
    for ticker in tickers:
        if ticker in ticker_map:
            cik, title = ticker_map[ticker]
            section = company_context(ticker, cik, title)
            if section:
                sections.append(section)
    if not sections:
        return ""
    sections.append(
        "Questions often resolve on company-reported or adjusted (non-GAAP) figures; check the resolution criteria."
    )
    return "\n\n".join(sections)
