"""Pure helpers for MV2's Market Pulse bot (stdlib only, so tests run without forecasting-tools).

This module decides:
- which LLMs to use (from environment variables / GitHub repo variables),
- whether the required secrets are present,
- which Market Pulse questions are due for a refresh before they are scored.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

# Env var -> forecasting-tools llm purpose.
LLM_ENV_KEYS = {
    "MV2_DEFAULT_MODEL": "default",
    "MV2_RESEARCHER": "researcher",
    "MV2_SUMMARIZER": "summarizer",
    "MV2_PARSER": "parser",
}

# At least one LLM route must exist. METACULUS_TOKEN alone uses the Metaculus proxy.
LLM_KEY_VARS = (
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "METACULUS_TOKEN",
)

DEFAULT_MARKET_PULSE_ID = "market-pulse-26q4"  # https://www.metaculus.com/tournament/market-pulse-26q4/


def llm_overrides(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return {purpose: model name} for every MV2_* model variable that is set and non-blank."""
    env = os.environ if env is None else env
    overrides: dict[str, str] = {}
    for var, purpose in LLM_ENV_KEYS.items():
        value = (env.get(var) or "").strip()
        if value:
            overrides[purpose] = value
    return overrides


def missing_secrets(env: Mapping[str, str] | None = None) -> list[str]:
    """Names of what is missing before the bot may forecast. Empty list means ready."""
    env = os.environ if env is None else env
    missing: list[str] = []
    if not (env.get("METACULUS_TOKEN") or "").strip():
        missing.append("METACULUS_TOKEN")
    if not any((env.get(name) or "").strip() for name in LLM_KEY_VARS):
        missing.append("an LLM key (OPENROUTER_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY)")
    return missing


def market_pulse_id(env: Mapping[str, str] | None = None, client_cls: Any = None) -> int | str:
    """The Market Pulse tournament: MV2_MARKET_PULSE_ID, else the library's current id, else 26Q4."""
    env = os.environ if env is None else env
    value = (env.get("MV2_MARKET_PULSE_ID") or "").strip()
    if value:
        return int(value) if value.isdigit() else value
    if client_cls is not None and getattr(client_cls, "CURRENT_MARKET_PULSE_ID", None):
        return getattr(client_cls, "CURRENT_MARKET_PULSE_ID")
    return DEFAULT_MARKET_PULSE_ID


def research_text(question: Any) -> str:
    """The question's own words (period label, title, background, criteria, fine print) used to pick market data.

    A group subquestion (e.g. one two-week period of a VIX question) keeps its period only in forecasting-tools'
    `group_question_option` (the Metaculus label); the description it shares with its siblings may list every
    period. The label goes first so the window reader finds this subquestion's own period.
    """
    names = ("group_question_option", "question_text", "background_info", "resolution_criteria", "fine_print")
    parts = (getattr(question, name, None) for name in names)
    return "\n".join(p for p in parts if isinstance(p, str) and p.strip())


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, str) and value.strip():
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def api_spot_scoring_time(question: Any) -> datetime | None:
    """Metaculus's own `spot_scoring_time` from the question's API JSON, if forecasting-tools kept it.

    Metaculus computes it as: the explicit spot scoring time, else the community-prediction reveal (if after the open
    time), else the close. Group subquestions are looked up by id under `group_of_questions`.
    """
    api_json = getattr(question, "api_json", None)
    if not isinstance(api_json, dict):
        return None
    candidates = [api_json.get("question")]
    qid = getattr(question, "id_of_question", None)
    group = api_json.get("group_of_questions")
    if qid is not None and isinstance(group, dict):
        candidates = [q for q in group.get("questions") or [] if isinstance(q, dict) and q.get("id") == qid] + candidates
    for entry in candidates:
        if isinstance(entry, dict) and (qid is None or entry.get("id") in (None, qid)):
            found = _as_utc(entry.get("spot_scoring_time"))
            if found is not None:
                return found
    return None


def scoring_time(question: Any) -> datetime | None:
    """When a forecast stops mattering.

    Metaculus's `spot_scoring_time` when the API gives it (never later than the close, after which nobody can
    forecast); otherwise the earlier of the community-prediction reveal and the close.
    """
    close = _as_utc(getattr(question, "close_time", None))
    spot = api_spot_scoring_time(question)
    if spot is not None:
        return min(spot, close) if close is not None else spot
    times = [t for t in (_as_utc(getattr(question, "cp_reveal_time", None)), close) if t is not None]
    return min(times) if times else None


def last_forecast_time(question: Any) -> datetime | None:
    try:
        return _as_utc(getattr(question, "timestamp_of_my_last_forecast", None))
    except Exception:  # the property can fail on unusual api_json; treat as unknown
        return None


def due_for_refresh(
    questions: Iterable[Any],
    now: datetime,
    window_hours: float = 13.0,
    min_age_hours: float = 6.0,
) -> list[Any]:
    """Questions scored within `window_hours` from `now` whose last forecast (if any) is at least `min_age_hours` old.

    Run twice a day with a 13h window, each question gets about one fresh forecast shortly before it is scored.
    """
    now = _as_utc(now) or datetime.now(timezone.utc)
    window_end = now + timedelta(hours=window_hours)
    due = []
    for question in questions:
        scored_at = scoring_time(question)
        if scored_at is None or scored_at <= now or scored_at > window_end:
            continue
        last = last_forecast_time(question)
        if last is not None and now - last < timedelta(hours=min_age_hours):
            continue
        due.append(question)
    return due
