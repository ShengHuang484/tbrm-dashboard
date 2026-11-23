import unittest

from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_baseline import compare


class ListingAndBaselineTests(unittest.TestCase):
    def setUp(self):
        self.days = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
        a, b, c, d = self.days
        self.history = {
            a: {"1101": 18, "1102": 15, "1103": 12},
            b: {"1101": 17, "1102": 14, "1103": 11},
            c: {"1101": 16, "1102": 13, "1103": 10},
            d: {"1101": 15, "1102": 12, "1103": 9},
        }
        self.listings = [
            self.listing("1101", a, None),
            self.listing("1102", a, c),
            self.listing("1102", c, None),
            self.listing("1103", a, d),
            self.listing("1104", a, None),
        ]

    @staticmethod
    def listing(code, start, end):
        return {"code": code, "listed_from": start, "delisted_on": end}

    def test_explicit_listing_intervals_exclude_relisting_and_delisting(self):
        report = audit_adjusted_lows(self.history, [], 2, listings=self.listings)
        first, last = report["sessions"]
        self.assertEqual(first["eligible_codes"], ["1101", "1103"])
        self.assertEqual(last["eligible_codes"], ["1101"])
        self.assertEqual(last["outside_active_listing"], 1)
        self.assertEqual(last["insufficient_listing_age"], 1)
        self.assertEqual(last["unquoted_current_listings"], 1)
        self.assertFalse(report["listing_universe_verified"])
        with self.assertRaisesRegex(ValueError, "overlapping"):
            audit_adjusted_lows(self.history, [], 2, listings=self.listings + self.listings[:1])

    def test_external_baseline_preserves_missing_coverage_and_disagreement(self):
        report = audit_adjusted_lows(self.history, [], 2, listings=self.listings)
        external = {day: {"1101": 100} for day in self.days}
        baseline = dict(provider="fixture", source_url="https://example.com",
                        adjustment_method="fixture", market_dates=self.days,
                        adjusted_closes=external)
        result = compare(report, baseline)
        self.assertEqual(result["sessions"][0]["missing_external_codes"], ["1103"])
        self.assertEqual(result["sessions"][1]["local_only_low_codes"], ["1101"])
        self.assertFalse(result["complete_agreement_on_research_cohort"])
        self.assertFalse(result["score_eligible"])
        with self.assertRaisesRegex(ValueError, "calendar differs"):
            compare(report, dict(baseline, market_dates=self.days[1:]))
