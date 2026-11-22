import unittest
from scripts.corporate_action_reconcile import reconcile_candidates

DATES = ["2026-06-01", "2026-06-02", "2026-06-03"]
EVENT = {"code": "2330", "ex_date": "2026-06-02", "prior_close": "100"}


class ReconcileTests(unittest.TestCase):
    def test_matching_price_is_still_research_only(self):
        r = reconcile_candidates([EVENT], {"2026-06-01": {"2330": 100}}, DATES)
        self.assertEqual(r["matched"], 1)
        self.assertFalse(r["score_eligible"])
        self.assertFalse(r["corporate_action_completeness_verified"])

    def test_mismatched_price_is_flagged(self):
        r = reconcile_candidates([EVENT], {"2026-06-01": {"2330": 90}}, DATES)
        self.assertEqual(r["checks"][0]["status"], "price_basis_mismatch")

    def test_missing_quote_is_flagged(self):
        r = reconcile_candidates([EVENT], {}, DATES)
        self.assertEqual(r["checks"][0]["status"], "missing_prior_close")

    def test_missing_calendar_date_is_flagged(self):
        r = reconcile_candidates([dict(EVENT, ex_date="2026-07-01")], {}, DATES)
        self.assertEqual(r["checks"][0]["status"], "no_prior_trading_day")


if __name__ == "__main__":
    unittest.main()
