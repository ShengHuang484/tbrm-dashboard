import unittest

from scripts.new_low_policy_sensitivity import compare_policies


class PolicySensitivityTest(unittest.TestCase):
    def test_sparse_stock_crosses_event_once_and_never_uses_future_close(self):
        days = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
        history = dict(zip(days, [
            {"1101": 100, "1102": 10}, {"1102": 10},
            {"1101": 51, "1102": 10}, {"1101": 50, "1102": 9}, {"1101": 49, "1102": 8},
        ]))
        action = {"code": "1101", "ex_date": days[2], "prior_close": "100", "reference_price": "50",
                  "source_url": "https://example.com", "verified": True, "event_type": "split"}
        report = compare_policies(history, [action], lookback=2)
        row = report["sessions"][1]
        self.assertEqual(row["additional_eligible_codes"], ["1101"])
        self.assertEqual(row["additional_adjusted_low_codes"], [])
        self.assertEqual(row["observed_raw_low_count"], 2)
        self.assertEqual(row["observed_adjusted_low_count"], 1)
        self.assertFalse(report["score_eligible"])

    def test_observed_policy_cannot_bridge_relisting(self):
        history = {"2026-01-02": {"1101": 10}, "2026-01-05": {"1101": 9},
                   "2026-01-06": {"1101": 8}, "2026-01-07": {"1101": 7}}
        listings = [{"code": "1101", "listed_from": "2026-01-02", "delisted_on": "2026-01-05"},
                    {"code": "1101", "listed_from": "2026-01-05", "delisted_on": None}]
        first, last = compare_policies(history, [], 2, listings=listings)["sessions"]
        self.assertEqual(first["observed_eligible_count"], 0)
        self.assertEqual(last["observed_eligible_count"], 1)
