import unittest

from scripts.capital_reduction_crosscheck import crosscheck


class ReductionCrosscheckTests(unittest.TestCase):
    def test_same_code_and_date_must_match_unrounded_reference(self):
        primary = {"start": "2025-10-22", "end": "2026-11-20",
                   "candidates": [{"code": "2832", "effective_date": "2025-11-03",
                                   "pre_halt_close": "36.00", "resumption_reference": "47.14"}]}
        peer = {"stock_id": "2832", "date": "2025-11-03",
                "ClosingPriceonTheLastTradingDay": 36, "PostReductionReferencePrice": 47.15}
        result = crosscheck(primary, [{"status": 200, "data": [peer]}])
        self.assertTrue(result["checks"][0]["prior_close_matches"])
        self.assertFalse(result["checks"][0]["resumption_reference_matches"])
        self.assertEqual(result["matching_prices"], 0)
        self.assertFalse(result["full_market_coverage_verified"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            crosscheck(primary, [{"status": 200, "data": [peer, peer]}])
