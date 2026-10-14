import unittest
from datetime import date

import vix_window as vw

TODAY = date(2026, 10, 13)  # a Tuesday


class ParseWindowTest(unittest.TestCase):
    def test_between_two_months(self):
        self.assertEqual(
            vw.parse_window("highest VIX between November 3 and November 14, 2026?", TODAY),
            (date(2026, 11, 3), date(2026, 11, 14)),
        )

    def test_from_iso_to_iso(self):
        self.assertEqual(
            vw.parse_window("VIX high from 2026-11-03 to 2026-11-14", TODAY),
            (date(2026, 11, 3), date(2026, 11, 14)),
        )

    def test_same_month_en_dash_range(self):
        self.assertEqual(
            vw.parse_window("the VIX over October 20–31, 2026", TODAY),
            (date(2026, 10, 20), date(2026, 10, 31)),
        )

    def test_same_month_and(self):
        self.assertEqual(
            vw.parse_window("VIX between November 3 and 14, 2026", TODAY),
            (date(2026, 11, 3), date(2026, 11, 14)),
        )

    def test_ignores_stray_resolution_date(self):
        text = (
            "This question resolves on November 20, 2026. "
            "What is the highest VIX between November 3 and November 14, 2026?"
        )
        self.assertEqual(vw.parse_window(text, TODAY), (date(2026, 11, 3), date(2026, 11, 14)))

    def test_single_date_is_none(self):
        self.assertIsNone(vw.parse_window("as of November 3, 2026 the VIX was 15", TODAY))

    def test_no_dates_is_none(self):
        self.assertIsNone(vw.parse_window("What will the VIX peak be this period?", TODAY))

    def test_year_inferred_for_near_future(self):
        self.assertEqual(
            vw.parse_window("VIX between November 3 and November 14", TODAY),
            (date(2026, 11, 3), date(2026, 11, 14)),
        )

    def test_too_wide_window_rejected(self):
        self.assertIsNone(vw.parse_window("from 2026-11-03 to 2027-02-03", TODAY))

    def test_empty_text_is_none(self):
        self.assertIsNone(vw.parse_window("", TODAY))

    def test_first_window_in_text_wins(self):
        # A group subquestion: its own period label comes first, then the shared text lists every period.
        text = "Oct 19 – Oct 30\nVIX biweekly maximum in Q4 2026?\nPeriods: Oct 5–16, Oct 19–30, Nov 2–13"
        self.assertEqual(vw.parse_window(text, TODAY), (date(2026, 10, 19), date(2026, 10, 30)))

    def test_label_across_new_year(self):
        self.assertEqual(vw.parse_window("Dec 28 – Jan 8", TODAY), (date(2026, 12, 28), date(2027, 1, 8)))


class TradingDaysTest(unittest.TestCase):
    def test_ahead_counts_weekdays(self):
        self.assertEqual(vw.trading_days_ahead(date(2026, 10, 13), date(2026, 10, 16)), 3)  # Wed, Thu, Fri

    def test_ahead_zero_when_not_future(self):
        self.assertEqual(vw.trading_days_ahead(date(2026, 10, 13), date(2026, 10, 13)), 0)

    def test_ahead_skips_weekend(self):
        self.assertEqual(vw.trading_days_ahead(date(2026, 10, 16), date(2026, 10, 19)), 1)  # Fri -> Mon

    def test_inclusive_counts_weekdays(self):
        self.assertEqual(vw.trading_days_inclusive(date(2026, 10, 13), date(2026, 10, 19)), 5)

    def test_inclusive_empty_when_reversed(self):
        self.assertEqual(vw.trading_days_inclusive(date(2026, 10, 19), date(2026, 10, 13)), 0)


if __name__ == "__main__":
    unittest.main()
