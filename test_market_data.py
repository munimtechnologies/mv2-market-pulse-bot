import unittest
from datetime import date, timedelta
from unittest import mock

import market_data as md


def vix_csv(n, close=15.0, high=16.5, reverse=False, bom=False):
    start = date(2026, 1, 1)
    lines = [f"{(start + timedelta(days=i)).strftime('%m/%d/%Y')},{close},{high},{close - 1},{close}" for i in range(n)]
    if reverse:
        lines.reverse()
    return ("﻿" if bom else "") + "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(lines) + "\n"


def treasury_csv(n):
    start = date(2026, 1, 1)
    rows = [
        f"{(start + timedelta(days=i)).strftime('%m/%d/%Y')},{4.0 + 0.01 * i:.2f},{'' if i == 0 else f'{4.0 + 0.01 * i:.2f}'}"
        for i in range(n)
    ]
    rows.reverse()  # Treasury lists the newest row first
    return 'Date,"3 Mo","10 Yr"\n' + "\n".join(rows) + "\n"


class PercentileTest(unittest.TestCase):
    def test_interpolates(self):
        self.assertAlmostEqual(md.percentile([4, 1, 3, 2], 50), 2.5)
        self.assertEqual(md.percentile([1, 2, 3, 4], 0), 1)
        self.assertEqual(md.percentile([1, 2, 3, 4], 100), 4)

    def test_single_value(self):
        self.assertEqual(md.percentile([7.0], 90), 7.0)


class VixTest(unittest.TestCase):
    def test_parse_sorts_oldest_first_and_handles_bom(self):
        rows = md.parse_vix_csv(vix_csv(3, reverse=True, bom=True))
        self.assertEqual([r["date"] for r in rows], [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)])
        self.assertEqual(rows[0]["close"], 15.0)

    def test_parse_skips_malformed_rows(self):
        text = "DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,1,2,1,1.5\nbad,1,2,3,4\n01/05/2026,1,2,1,\n"
        self.assertEqual(len(md.parse_vix_csv(text)), 1)

    def test_forward_max_ratios(self):
        rows = [{"close": 10.0, "high": h} for h in (10, 12, 11, 15)]
        self.assertEqual(md.forward_max_ratios(rows, 2), [1.2, 1.5])

    def test_summary_too_short_is_empty(self):
        self.assertEqual(md.summarize_vix(md.parse_vix_csv(vix_csv(20))), "")

    def test_summary_levels_and_base_rate(self):
        text = md.summarize_vix(md.parse_vix_csv(vix_csv(100)))
        self.assertIn("close 15.00", text)
        self.assertIn("16.50 / 16.50 / 16.50", text)
        self.assertIn("p50 16.50", text)


class TreasuryTest(unittest.TestCase):
    def test_parse_sorts_and_keeps_blanks_as_none(self):
        rows = md.parse_treasury_csv(treasury_csv(3))
        self.assertEqual(rows[0]["date"], date(2026, 1, 1))
        self.assertIsNone(rows[0]["10 Yr"])
        self.assertAlmostEqual(rows[2]["10 Yr"], 4.02)

    def test_summary_changes_and_base_rate(self):
        # 31 rows, the first 10 Yr blank: 20 ten-day changes, enough for the base rate.
        text = md.summarize_yields(md.parse_treasury_csv(treasury_csv(31)))
        self.assertIn("10 Yr 4.30%", text)
        self.assertIn("+5 bp vs 5 trading days ago", text)
        self.assertIn("+20 bp vs 20 trading days ago", text)
        self.assertIn("p50 +10", text)
        self.assertNotIn("2 Yr", text)

    def test_summary_too_short_is_empty(self):
        self.assertEqual(md.summarize_yields(md.parse_treasury_csv(treasury_csv(10))), "")


class MarketContextTest(unittest.TestCase):
    def test_picks_sections_by_topic(self):
        with mock.patch.object(md, "vix_context", return_value="V"), mock.patch.object(
            md, "treasury_context", return_value="T"
        ):
            self.assertIn("V", md.market_context("What will the VIX peak be?"))
            self.assertNotIn("T", md.market_context("What will the VIX peak be?").split(":\n", 1)[1])
            both = md.market_context("Will the 10-year Treasury yield rise while the VIX falls?")
            self.assertTrue(both.endswith("V\n\nT"))
            self.assertEqual(md.market_context("Will NVDA beat AMD this quarter?"), "")

    def test_sources_down_gives_empty(self):
        with mock.patch.object(md, "vix_context", return_value=""):
            self.assertEqual(md.market_context("VIX peak"), "")


if __name__ == "__main__":
    unittest.main()
