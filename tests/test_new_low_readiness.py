import unittest
from scripts.new_low_readiness import evaluate


class ReadinessTests(unittest.TestCase):
    def test_all_structural_checks_still_do_not_enable_scoring(self):
        evidence = {
            "price_reconciliation": {
                "candidate_count": 961, "matched": 961,
                "price_precision_audit": {"exact_price_matches": 961},
            },
            "raw_universe_audit": {
                "raw_history_structurally_valid": True,
                "latest_day_codes": 1000,
                "latest_codes_with_252_consecutive_prior_trading_closes": 1000,
                "internal_gap_code_count": 0,
            },
            "effective_date_review_queue": {"exception_count": 0},
            "identity_audit": {"identity_audit_passed": True},
        }
        result = evaluate(evidence)
        self.assertFalse(result["score_eligible"])
        self.assertEqual(result["live_points_enabled"], 45)
        self.assertIn("capital_reduction_split_merger_event_completeness_unverified",
                      result["blocking_reasons"])

    def test_missing_stock_coverage_is_explicit(self):
        evidence = {
            "price_reconciliation": {
                "candidate_count": 2, "matched": 1,
                "price_precision_audit": {"exact_price_matches": 1},
            },
            "raw_universe_audit": {
                "raw_history_structurally_valid": True,
                "latest_day_codes": 100,
                "latest_codes_with_252_consecutive_prior_trading_closes": 80,
                "internal_gap_code_count": 5,
            },
            "effective_date_review_queue": {"exception_count": 1},
            "identity_audit": {"identity_audit_passed": True},
        }
        result = evaluate(evidence)
        self.assertEqual(result["stocks_excluded_by_strict_252_day_rule"], 20)
        self.assertIn("unclassified_internal_missing_quotes", result["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
