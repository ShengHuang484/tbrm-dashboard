import unittest

from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_rights_scenario import compare


class RightsScenarioTest(unittest.TestCase):
    def test_above_market_subscription_can_change_low_and_preserves_main_report(self):
        a, b, c = "2026-06-09", "2026-06-10", "2026-06-11"
        history = {a: {"1312": "9.98"}, b: {"1312": "13.20"}, c: {"1312": "10"}}
        event = dict(code="1312", ex_date=c, prior_close="13.20", reference_price="13.40",
                     event_type="monthly_ex_right_reconciled", verified=True,
                     source_url="https://example.org")
        report = dict(audit_adjusted_lows(history, [event], 2), applied_events=[event])
        evidence = dict(code="1312", effective_date=c, prior_close="13.20",
                        official_reference="13.40", dividend_only_reference="13.20",
                        auction_basis="13.20", subscription_price="14.00")
        self.assertEqual(compare(history, report, evidence)["changed_sessions"][0]["removed"], ["1312"])
        self.assertEqual(event["reference_price"], "13.40")
        with self.assertRaisesRegex(ValueError, "above-market"):
            compare(history, report, dict(evidence, subscription_price="13.10"))
