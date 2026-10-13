import unittest
from datetime import datetime, timedelta, timezone

import mv2_config as cfg

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


class Q:
    def __init__(self, close=None, reveal=None, last=None, broken=False):
        self.close_time = close
        self.cp_reveal_time = reveal
        self._last = last
        self._broken = broken

    @property
    def timestamp_of_my_last_forecast(self):
        if self._broken:
            raise KeyError("my_forecasts")
        return self._last


class LlmOverridesTest(unittest.TestCase):
    def test_empty_env_gives_no_overrides(self):
        self.assertEqual(cfg.llm_overrides({}), {})

    def test_blank_values_are_ignored(self):
        self.assertEqual(cfg.llm_overrides({"MV2_DEFAULT_MODEL": "  ", "MV2_PARSER": ""}), {})

    def test_set_values_map_to_purposes(self):
        env = {"MV2_DEFAULT_MODEL": "openrouter/x/y ", "MV2_RESEARCHER": "asknews/news-summaries"}
        self.assertEqual(
            cfg.llm_overrides(env),
            {"default": "openrouter/x/y", "researcher": "asknews/news-summaries"},
        )


class MissingSecretsTest(unittest.TestCase):
    def test_nothing_set(self):
        missing = cfg.missing_secrets({})
        self.assertEqual(len(missing), 2)
        self.assertIn("METACULUS_TOKEN", missing)

    def test_token_alone_is_enough(self):
        # The Metaculus proxy serves models with just the token.
        self.assertEqual(cfg.missing_secrets({"METACULUS_TOKEN": "t"}), [])

    def test_llm_key_without_token(self):
        self.assertEqual(cfg.missing_secrets({"OPENROUTER_API_KEY": "k"}), ["METACULUS_TOKEN"])


class MarketPulseIdTest(unittest.TestCase):
    def test_fallback(self):
        self.assertEqual(cfg.market_pulse_id({}), "market-pulse-26q4")

    def test_library_constant_wins_over_fallback(self):
        class Client:
            CURRENT_MARKET_PULSE_ID = "market-pulse-27q1"

        self.assertEqual(cfg.market_pulse_id({}, Client), "market-pulse-27q1")

    def test_env_wins_and_digits_become_int(self):
        class Client:
            CURRENT_MARKET_PULSE_ID = "market-pulse-27q1"

        self.assertEqual(cfg.market_pulse_id({"MV2_MARKET_PULSE_ID": "123"}, Client), 123)
        self.assertEqual(cfg.market_pulse_id({"MV2_MARKET_PULSE_ID": "mp"}, Client), "mp")


class ResearchTextTest(unittest.TestCase):
    def test_joins_present_fields(self):
        q = Q()
        q.question_text = "VIX peak?"
        q.background_info = "  "
        q.resolution_criteria = "Cboe close"
        q.fine_print = None
        self.assertEqual(cfg.research_text(q), "VIX peak?\nCboe close")


class DueForRefreshTest(unittest.TestCase):
    def test_closing_soon_never_forecast_is_due(self):
        q = Q(close=NOW + timedelta(hours=5))
        self.assertEqual(cfg.due_for_refresh([q], NOW), [q])

    def test_closing_later_than_window_is_not_due(self):
        q = Q(close=NOW + timedelta(hours=20))
        self.assertEqual(cfg.due_for_refresh([q], NOW), [])

    def test_already_closed_is_not_due(self):
        q = Q(close=NOW - timedelta(minutes=1))
        self.assertEqual(cfg.due_for_refresh([q], NOW), [])

    def test_recent_forecast_is_not_due(self):
        q = Q(close=NOW + timedelta(hours=5), last=NOW - timedelta(hours=2))
        self.assertEqual(cfg.due_for_refresh([q], NOW), [])

    def test_old_forecast_is_due(self):
        q = Q(close=NOW + timedelta(hours=5), last=NOW - timedelta(days=3))
        self.assertEqual(cfg.due_for_refresh([q], NOW), [q])

    def test_reveal_before_close_counts(self):
        # Scored at the community-prediction reveal, which is inside the window even though close is not.
        q = Q(close=NOW + timedelta(days=10), reveal=NOW + timedelta(hours=3))
        self.assertEqual(cfg.due_for_refresh([q], NOW), [q])

    def test_naive_datetimes_are_treated_as_utc(self):
        q = Q(close=(NOW + timedelta(hours=5)).replace(tzinfo=None))
        self.assertEqual(cfg.due_for_refresh([q], NOW), [q])

    def test_no_times_is_not_due(self):
        self.assertEqual(cfg.due_for_refresh([Q()], NOW), [])

    def test_broken_last_forecast_property_is_unknown(self):
        q = Q(close=NOW + timedelta(hours=5), broken=True)
        self.assertEqual(cfg.due_for_refresh([q], NOW), [q])


if __name__ == "__main__":
    unittest.main()
