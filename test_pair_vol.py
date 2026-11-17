import unittest
from datetime import date

import pair_vol as pv


class FindLegsTest(unittest.TestCase):
    def test_pairs_in_order_of_mention(self):
        self.assertEqual(pv.find_legs("Gold − ES, percentage points"), ["Gold", "S&P 500"])
        self.assertEqual(pv.find_legs("NQ − ES"), ["Nasdaq-100", "S&P 500"])
        self.assertEqual(pv.find_legs("CL vs ES"), ["Crude oil", "S&P 500"])
        self.assertEqual(pv.find_legs("S&P 500 against the Nasdaq-100"), ["S&P 500", "Nasdaq-100"])

    def test_lowercase_ticker_words_are_not_legs(self):
        self.assertEqual(pv.find_legs("yes, es, cl and gc are words here"), [])
        self.assertEqual(pv.find_legs("What will the VIX peak be?"), [])
        self.assertEqual(pv.find_legs("Gold price in USD"), ["Gold"])


class ParseTest(unittest.TestCase):
    def test_single_column_file_with_bom(self):
        text = "﻿DATE,GVZ\n10/09/2026,22.79\n10/13/2026,22.09\n10/12/2026,22.48\nbad,1\n10/14/2026,\n"
        self.assertEqual(
            pv.parse_cboe_csv(text, "GVZ"),
            [(date(2026, 10, 9), 22.79), (date(2026, 10, 12), 22.48), (date(2026, 10, 13), 22.09)],
        )

    def test_ohlc_file_uses_close(self):
        text = "DATE,OPEN,HIGH,LOW,CLOSE\n10/13/2026,1,2,0.5,18.2\n"
        self.assertEqual(pv.parse_cboe_csv(text, "VXN"), [(date(2026, 10, 13), 18.2)])


class MathTest(unittest.TestCase):
    def test_spread_sd(self):
        self.assertAlmostEqual(pv.spread_sd(30, 40, 0.0, 252), 50.0)
        self.assertAlmostEqual(pv.spread_sd(20, 20, 1.0, 10), 0.0)
        self.assertAlmostEqual(pv.spread_sd(30, 40, 0.5, 63), 18.02776, places=4)

    def test_window_days(self):
        self.assertEqual(pv.window_days(None), 10)
        self.assertEqual(pv.window_days((date(2026, 10, 19), date(2026, 10, 30))), 10)
        self.assertEqual(pv.window_days((date(2026, 11, 23), date(2026, 12, 4))), 9)  # Thanksgiving
        self.assertEqual(pv.window_days((date(2026, 10, 17), date(2026, 10, 18))), 10)  # a weekend only


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.series = {
            "Nasdaq-100": [(date(2026, 10, 9), 10.0), (date(2026, 10, 12), 30.0), (date(2026, 10, 13), 30.0)],
            "S&P 500": [(date(2026, 10, 13), 40.0)],
        }

    def test_text(self):
        text = pv.summarize_pair(["Nasdaq-100", "S&P 500"], self.series, 63)
        self.assertIn(
            "Nasdaq-100 (VXN) 30.00 on 2026-10-13, 1-year median 30.00; S&P 500 (VIX) 40.00 on 2026-10-13, "
            "1-year median 40.00.",
            text,
        )
        self.assertIn("No question window found in the text; using 63 trading days.", text)
        self.assertIn("over 63 trading days: Nasdaq-100 15.00%, S&P 500 20.00%.", text)
        self.assertIn("Nasdaq-100 return minus S&P 500 return", text)
        self.assertIn("corr 0.0: sd 25.00, 10th to 90th percentile -32.04 to +32.04", text)
        self.assertIn("corr 0.5: sd 18.03, 10th to 90th percentile -23.10 to +23.10", text)
        self.assertIn("corr 0.9: sd 9.22, 10th to 90th percentile -11.82 to +11.82", text)
        self.assertNotIn("GLD", text)

    def test_window_label_and_etf_note(self):
        series = {"Gold": [(date(2026, 10, 13), 22.0)], "S&P 500": [(date(2026, 10, 13), 18.0)]}
        window = (date(2026, 10, 19), date(2026, 10, 30))
        text = pv.summarize_pair(["Gold", "S&P 500"], series, pv.window_days(window), window=window)
        self.assertIn("Question window 2026-10-19 to 2026-10-30: 10 trading days.", text)
        self.assertIn("GLD and USO", text)

    def test_missing_leg_is_empty(self):
        self.assertEqual(pv.summarize_pair(["Nasdaq-100", "Gold"], self.series, 10), "")
        self.assertEqual(pv.summarize_pair(["Nasdaq-100"], self.series, 10), "")


if __name__ == "__main__":
    unittest.main()
