import unittest
from datetime import date
from unittest import mock

import sec_filings as sec


def fact(start, end, val, filed="2026-01-01", form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


# Apple-shaped fiscal year (late September year end), values in $B for readability.
FACTS = [
    fact("2024-09-29", "2025-09-27", 416.0, "2025-10-31", "10-K"),
    fact("2024-09-29", "2025-06-28", 313.0, "2025-08-01"),
    fact("2024-09-29", "2024-12-28", 124.0, "2025-01-31"),
    fact("2024-12-29", "2025-03-29", 95.0, "2025-05-02"),
    fact("2025-03-30", "2025-06-28", 94.0, "2025-08-01"),
    fact("2025-09-28", "2025-12-27", 143.0, "2026-01-30"),
    fact("2025-09-28", "2026-03-28", 254.0, "2026-05-01"),  # six months: ignored
    fact("2025-12-28", "2026-03-28", 111.0, "2026-05-01"),
    fact("2025-03-30", "2025-06-28", 94.5, "2026-07-31"),  # restated later: latest filing wins
    fact("2026-03-29", "2026-06-27", 109.0, "2026-07-31"),
    {"start": "bad", "end": "2026-06-27", "val": 1.0},
    fact("2026-03-29", "2026-06-27", "n/a"),
]


class FindTickersTest(unittest.TestCase):
    def test_parenthesized_exchange_and_names_in_order(self):
        text = "Will NVIDIA (NVDA) report more revenue than Apple, or will (NASDAQ: AMD) beat NYSE: ORCL?"
        self.assertEqual(sec.find_tickers(text), ["NVDA", "AAPL", "AMD", "ORCL"])

    def test_stop_words_and_lowercase_words_are_not_tickers(self):
        self.assertEqual(sec.find_tickers("Diluted earnings per share (EPS) in (USD), an apple a day"), [])

    def test_meta_needs_full_name_or_ticker(self):
        self.assertEqual(sec.find_tickers("Meta question about Meta Platforms"), ["META"])


class TickerMapTest(unittest.TestCase):
    def test_parse(self):
        data = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, "1": {"bad": 1}}
        self.assertEqual(sec.parse_ticker_map(data), {"AAPL": (320193, "Apple Inc.")})


class QuarterlyValuesTest(unittest.TestCase):
    def setUp(self):
        self.rows = sec.quarterly_values(FACTS)

    def test_quarters_oldest_first_with_derived_q4(self):
        self.assertEqual(
            [(r["end"], r["val"], r["derived"]) for r in self.rows],
            [
                (date(2024, 12, 28), 124.0, False),
                (date(2025, 3, 29), 95.0, False),
                (date(2025, 6, 28), 94.5, False),
                (date(2025, 9, 27), 103.0, True),
                (date(2025, 12, 27), 143.0, False),
                (date(2026, 3, 28), 111.0, False),
                (date(2026, 6, 27), 109.0, False),
            ],
        )

    def test_annual_with_reported_q4_is_not_derived(self):
        rows = sec.quarterly_values(FACTS + [fact("2025-06-29", "2025-09-27", 102.0, "2025-10-31", "10-K")])
        q4 = [r for r in rows if r["end"] == date(2025, 9, 27)]
        self.assertEqual(q4, [{"end": date(2025, 9, 27), "val": 102.0, "derived": False}])


class FormatTest(unittest.TestCase):
    def test_revenue_lines_with_yoy(self):
        rows = sec.quarterly_values([{**f, "val": f["val"] * 1e9} if isinstance(f.get("val"), float) else f for f in FACTS])
        text = sec.format_series(rows, "revenue", count=3)
        lines = text.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("quarter ended 2026-06-27: $109.00B (YoY +15.3%)", lines[-1])
        self.assertIn("2026-03-28: $111.00B (YoY +16.8%)", lines[-2])

    def test_eps_lines_and_derived_note(self):
        rows = [
            {"end": date(2025, 6, 28), "val": 1.57, "derived": False},
            {"end": date(2025, 9, 27), "val": 1.85, "derived": True},
            {"end": date(2026, 6, 27), "val": 2.02, "derived": False},
        ]
        text = sec.summarize_company("AAPL", "Apple Inc.", [], rows)
        self.assertIn("Apple Inc. (AAPL)", text)
        self.assertIn("$1.85*", text)
        self.assertIn("2026-06-27: $2.02 (a year earlier $1.57)", text)
        self.assertIn("derived as fiscal year minus the first nine months", text)

    def test_small_revenue_in_millions(self):
        rows = [{"end": date(2026, 6, 27), "val": 45_600_000.0, "derived": False}]
        self.assertIn("$45.6M", sec.format_series(rows, "revenue"))

    def test_nothing_gives_empty(self):
        self.assertEqual(sec.summarize_company("X", "X", [], []), "")


class EarningsContextTest(unittest.TestCase):
    def test_only_for_earnings_questions_naming_a_company(self):
        with mock.patch.object(sec, "_fetch_json", side_effect=AssertionError("no fetch expected")):
            self.assertEqual(sec.earnings_context("Will the VIX close above 20?"), "")
            self.assertEqual(sec.earnings_context("Will S&P 500 earnings grow?"), "")

    def test_builds_sections_from_sec_data(self):
        concept = {"units": {"USD": [dict(f, val=f["val"] * 1e9) for f in FACTS if isinstance(f.get("val"), float) and "start" in f and f["start"] != "bad"]}}

        def fake_fetch(url, timeout=20.0):
            if url == sec.TICKERS_URL:
                return {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
            if "Revenues" in url and "Contract" not in url:
                return concept
            raise OSError("404")

        with mock.patch.object(sec, "_fetch_json", side_effect=fake_fetch):
            text = sec.earnings_context("What will Apple's revenue be for the quarter ending December 2026?")
        self.assertIn("Apple Inc. (AAPL)", text)
        self.assertIn("us-gaap:Revenues", text)
        self.assertIn("$109.00B", text)
        self.assertNotIn("Diluted EPS", text)
        self.assertIn("non-GAAP", text)

    def test_ticker_list_down_gives_empty(self):
        with mock.patch.object(sec, "_fetch_json", side_effect=OSError("down")):
            self.assertEqual(sec.earnings_context("NVIDIA (NVDA) revenue?"), "")


if __name__ == "__main__":
    unittest.main()
