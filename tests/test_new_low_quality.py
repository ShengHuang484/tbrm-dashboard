"""Fail-closed checks for the research-only 52-week new-low series.

Run: python -m unittest discover -s tests -p 'test_new_low_quality.py'
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NewLowQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "data" / "new_low.json").read_text(encoding="utf-8"))

    def test_calendar_completeness(self):
        r = self.report
        self.assertEqual(r["valid_days"] + r["missing_days"], r["required_days"])
        self.assertEqual(r["required_days"], 262)

    def test_raw_prices_must_not_be_scored(self):
        r = self.report
        if r.get("method") == "raw_close_proxy" or not r.get("corporate_action_verified", False):
            self.assertFalse(r.get("score_eligible", False))

    def test_dynamic_universe_research_consistency(self):
        r = self.report
        d = r.get("dynamic_universe_research_only")
        if d is None:
            self.skipTest("Awaiting complete 262-day history")
        self.assertEqual(r["valid_days"], 262)
        self.assertFalse(d["score_eligible"])
        for key in ("counts", "eligible_stock_counts", "missing_lookback_counts", "coverage_by_day"):
            self.assertEqual(len(d[key]), 10, key)
        for count, eligible, missing, coverage, total in zip(
            d["counts"], d["eligible_stock_counts"], d["missing_lookback_counts"],
            d["coverage_by_day"], r["latest_10_daily_universe_counts"]
        ):
            self.assertLessEqual(count, eligible)
            self.assertLessEqual(eligible + missing, total)
            self.assertAlmostEqual(coverage, eligible / total, delta=0.00002)

    def test_trend_arithmetic(self):
        r = self.report
        if len(r.get("counts", [])) != 10:
            self.skipTest("Awaiting ten-day research counts")
        counts = r["counts"]
        self.assertAlmostEqual(r["previous_avg"], sum(counts[:5]) / 5)
        self.assertAlmostEqual(r["recent_avg"], sum(counts[5:]) / 5)
        if r["previous_avg"] > 0:
            self.assertAlmostEqual(
                r["decline_pct"],
                (r["previous_avg"] - r["recent_avg"]) / r["previous_avg"] * 100,
                places=5,
            )


if __name__ == "__main__":
    unittest.main()
