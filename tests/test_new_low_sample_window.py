import unittest

from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_sample_window import check_window


class SampleWindowTests(unittest.TestCase):
    def setUp(self):
        self.days = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"]
        self.history = {d: {"1101": v} for d, v in zip(self.days, [8, 10, 7, 6])}
        self.report = dict(audit_adjusted_lows(self.history, [], 2), applied_events=[])

    def inspect(self, values):
        baseline = dict(market_dates=self.days, provider="fixture", source_url="https://example.com",
                        adjusted_closes={d: {"1101": v} for d, v in zip(self.days, values)
                                         if v is not None})
        return check_window(self.history, self.report, baseline, "1101", self.days[2], "0.01")

    def test_missing_prior_prevents_positive_even_with_future_quote(self):
        result = self.inspect([None, 20, 14, 1])
        self.assertIsNone(result["external_low_on_displayed_prices"])
        self.assertEqual(result["missing_dates"], self.days[:1])
        self.assertFalse(result["price_ratio_mismatch_dates"])

    def test_tie_disproves_strict_low_and_flags_ratio_difference(self):
        result = self.inspect([None, 14, 14, None])
        self.assertFalse(result["external_low_on_displayed_prices"])
        self.assertEqual(result["price_ratio_mismatch_dates"], self.days[1:2])
        result = self.inspect([16, 20, 14, None])
        self.assertTrue(result["external_low_on_displayed_prices"])
