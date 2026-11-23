import unittest

from scripts.missing_close_audit import audit


class MissingCloseAuditTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = "2026-01-08", "2026-01-09", "2026-01-12"
        self.history = {self.a: {}, self.b: {}, self.c: {"1101": 20, "1102": 30}}
        self.report = dict(market_dates=list(self.history), lookback=2,
                           listing_intervals=[
                               dict(code="1101", listed_from=self.a, delisted_on=None),
                               dict(code="1102", listed_from=self.c, delisted_on=None)],
                           sessions=[dict(date=self.c, eligible_codes=[], adjusted_low_count=0)])
        self.lifecycle = dict(trading_stop_checks=[], coverage=dict(missing_close_pairs=2))
        self.activity = dict(code="1101", conflicting_dates=[], absent_close_reason={})

    def test_groups_market_sessions_and_keeps_short_listing_outside_missing_pairs(self):
        result = audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")
        [group] = result["groups"]
        self.assertEqual(group["pairs"], 2)
        self.assertEqual(group["sole_gap_study_dates"], [self.c])
        self.assertEqual(result["study_day_impact"][0]["insufficient_listing_age"], 1)
        self.assertFalse(result["score_eligible"])

    def test_activity_evidence_does_not_convert_unknown_into_a_halt(self):
        self.activity["absent_close_reason"][self.b] = "activity_without_close"
        result = audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")
        self.assertEqual(result["classification"]["unknown"]["pairs"], 1)
        self.assertEqual(result["study_day_impact"][0]["unknown_only_exclusions"], 0)
        self.activity["absent_close_reason"][self.c] = "zero_reported_activity"
        with self.assertRaisesRegex(ValueError, "overlapping"):
            audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")
