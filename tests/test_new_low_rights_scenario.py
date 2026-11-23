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

    def test_external_transition_distinguishes_references_at_display_precision(self):
        import json
        from pathlib import Path

        evidence = json.loads(Path("research/1312_rights_basis.json").read_text())
        days = ["2026-06-10", "2026-06-11"]
        history = dict(zip(days, [{"1312": 13.2}, {"1312": 12.85}]))
        event = dict(code="1312", ex_date=days[1], prior_close="13.20", reference_price="13.40",
                     event_type="monthly_ex_right_reconciled", verified=True,
                     source_url=evidence["official_method_source"])
        report = dict(audit_adjusted_lows(history, [event], 1), applied_events=[event])
        result = compare(history, report, evidence)["external_transition"]
        self.assertFalse(result["official_reference"]["agrees_with_display_precision"])
        self.assertTrue(result["zero_rights_value"]["agrees_with_display_precision"])
