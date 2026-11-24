import unittest

from scripts.issuer_cash_scenario import compare_cash_basis
from scripts.new_low_adjusted_audit import audit_adjusted_lows


class CashBasisTests(unittest.TestCase):
    def setUp(self):
        a, b = "2026-01-05", "2026-01-06"
        self.history = {a: {"1101": 100}, b: {"1101": 95}}
        event = dict(code="1101", ex_date=b, prior_close="100", reference_price="94.99",
                     event_type="monthly_ex_right_reconciled", verified=True,
                     source_url="https://example.com/ex")
        self.report = dict(audit_adjusted_lows(self.history, [event], 1), applied_events=[event])
        self.baseline = dict(provider="fixture", source_url="https://example.com",
                             market_dates=[a, b], adjusted_closes={a: {"1101": 95}, b: {"1101": 95}})
        self.payment = dict(ex_date=b, cash_per_common_share_twd="5.000001")
        self.day = b

    def compare(self, payments):
        evidence = dict(code="1101", source_url="https://example.com/issuer",
                        cash_only_distributions=payments)
        return compare_cash_basis(self.history, self.report, self.baseline, evidence, self.day, ".001")

    def test_cash_precision_only_changes_counterfactual(self):
        result = self.compare([self.payment])
        self.assertEqual(len(result["official_basis_mismatch_dates"]), 1)
        self.assertEqual(result["issuer_cash_basis_mismatch_dates"], [])
        self.assertEqual(self.report["applied_events"][0]["reference_price"], "94.99")
        self.assertFalse(result["score_eligible"])

    def test_does_not_replace_a_split_or_accept_duplicate_or_unmatched_dates(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.compare([self.payment, self.payment])
        with self.assertRaisesRegex(ValueError, "missing"):
            self.compare([dict(self.payment, ex_date="2026-01-07")])
        self.report["applied_events"][0]["event_type"] = "split"
        with self.assertRaisesRegex(ValueError, "ex-dividend"):
            self.compare([self.payment])
