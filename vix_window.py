"""Read the date window from a Market Pulse VIX question (stdlib only).

Market Pulse asks things like "What will be the highest value the VIX reaches
between November 3 and November 14, 2026?" The window can start in the future and
is usually about two weeks long. Finding it lets the bot build the base rate over
the right horizon (the trading days up to the end of that window) instead of a
fixed 10 trading days.

Nothing here fetches anything or gives advice; it only reads dates from text and
counts trading days (weekdays minus the NYSE full-day holidays listed below for
2026-2028; after 2028 only weekends are skipped).
"""

from __future__ import annotations

from datetime import date, timedelta
import re

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"

# "November 3, 2026" / "Nov 3 2026" / "November 3" (year optional)
_MDY = re.compile(
    rf"\b(?P<mon>{_MONTH_RE})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?\b",
    re.IGNORECASE,
)
# "2026-11-03"
_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<mon>\d{1,2})-(?P<day>\d{1,2})\b")
# same-month range "November 3-14, 2026" / "November 3 to 14" / "November 3 and 14, 2026"
_MD_RANGE = re.compile(
    rf"\b(?P<mon>{_MONTH_RE})\.?\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:[-–—]|to|through|and)\s*"
    rf"(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?\b",
    re.IGNORECASE,
)
# a gap of text that is only a window connective ("between X and Y", "from X to Y")
_CONNECTIVE = re.compile(r"^\s*(?:and|to|through|until|[-–—])\s*$", re.IGNORECASE)

MAX_SPAN_DAYS = 45

# NYSE full-day closures (nyse.com/markets/hours-calendars, checked 2026-10-14). Cboe's U.S. options market closes
# on the same days, so the VIX daily history has no row for them. Early-close days (e.g. the day after Thanksgiving)
# are still trading days.
NYSE_HOLIDAYS = frozenset({
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
    # 2028 (January 1 is a Saturday, so there is no New Year's closure)
    date(2028, 1, 17), date(2028, 2, 21), date(2028, 4, 14), date(2028, 5, 29), date(2028, 6, 19),
    date(2028, 7, 4), date(2028, 9, 4), date(2028, 11, 23), date(2028, 12, 25),
})


def is_trading_day(day: date) -> bool:
    """A weekday that is not a listed NYSE holiday."""
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _infer_year(month: int, day: int, today: date) -> int:
    """Pick the year for a date written without one: this year, or next if it is well past."""
    guess = _safe_date(today.year, month, day)
    if guess is not None and guess < today - timedelta(days=180):
        return today.year + 1
    return today.year


def _scan_dates(text: str, today: date) -> list[tuple[int, int, date]]:
    """Every full date in the text as (start_pos, end_pos, date), sorted by position."""
    found: list[tuple[int, int, date]] = []
    for m in _ISO.finditer(text):
        day = _safe_date(int(m["year"]), int(m["mon"]), int(m["day"]))
        if day is not None:
            found.append((m.start(), m.end(), day))
    for m in _MDY.finditer(text):
        month = MONTHS[m["mon"].lower()]
        year = int(m["year"]) if m["year"] else _infer_year(month, int(m["day"]), today)
        day = _safe_date(year, month, int(m["day"]))
        if day is not None:
            found.append((m.start(), m.end(), day))
    found.sort(key=lambda t: t[0])
    return found


def _valid(window: tuple[date, date], today: date) -> bool:
    start, end = window
    span = (end - start).days
    return 0 <= span <= MAX_SPAN_DAYS and end >= today - timedelta(days=7) and start <= today + timedelta(days=400)


def _range_from_md(m: "re.Match[str]", today: date) -> tuple[date, date] | None:
    month = MONTHS[m["mon"].lower()]
    year = int(m["year"]) if m["year"] else _infer_year(month, int(m["d1"]), today)
    d1 = _safe_date(year, month, int(m["d1"]))
    d2 = _safe_date(year, month, int(m["d2"]))
    if d1 is None or d2 is None:
        return None
    return (d1, d2) if d1 <= d2 else (d2, d1)


def parse_window(text: str, today: date) -> tuple[date, date] | None:
    """The (start, end) window the question asks about, or None if it can't be read.

    Handles "Month D1-D2, Year" same-month ranges and two dates joined by a
    connective ("between X and Y", "from X to Y", "Oct 19 – Oct 30"). A connective
    is required, so a stray resolution date elsewhere in the text is not mistaken
    for the window. When the text holds several windows (a group question's shared
    description can list every period), the first one in the text wins, so the
    caller puts the subquestion's own period label first.
    """
    if not text:
        return None
    candidates: list[tuple[int, tuple[date, date]]] = []
    for m in _MD_RANGE.finditer(text):
        window = _range_from_md(m, today)
        if window is not None:
            candidates.append((m.start(), window))
    dated = _scan_dates(text, today)
    for (s1, e1, d1), (s2, e2, d2) in zip(dated, dated[1:]):
        if _CONNECTIVE.match(text[e1:s2]):
            candidates.append((s1, (d1, d2) if d1 <= d2 else (d2, d1)))
    for _, window in sorted(candidates, key=lambda c: c[0]):
        if _valid(window, today):
            return window
    return None


def trading_days_ahead(today: date, target: date) -> int:
    """Trading days strictly after `today` up to and including `target` (0 if target <= today)."""
    if target <= today:
        return 0
    count = 0
    day = today + timedelta(days=1)
    while day <= target:
        if is_trading_day(day):
            count += 1
        day += timedelta(days=1)
    return count


def trading_days_inclusive(start: date, end: date) -> int:
    """Trading days in [start, end] inclusive (0 if end < start)."""
    if end < start:
        return 0
    count = 0
    day = start
    while day <= end:
        if is_trading_day(day):
            count += 1
        day += timedelta(days=1)
    return count
