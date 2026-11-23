import unittest

from scripts.twse_reduction_audit import FIELDS, inventory


class ReductionAuditTest(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "title": "115年11月01日 至 115年11月30日 股票減資恢復買賣參考價格",
            "stat": "OK",
            "fields": list(FIELDS),
            "data": [["115/11/23", "1808", "31.00", "36.25", "--", "退還股款"]],
        }
        self.bounds = "2026-11-01", "2026-11-30"

    def test_resumption_and_rights_references_remain_separate(self):
        rows = inventory(self.payload, *self.bounds)
        self.assertEqual(rows[0]["effective_date"], "2026-11-23")
        self.assertEqual(rows[0]["resumption_reference"], "36.25")
        self.assertEqual(rows[0]["rights_reference"], "--")
        self.assertFalse(rows[0]["verified"])

    def test_rejects_ignored_query_bounds_and_duplicate_events(self):
        with self.assertRaisesRegex(ValueError, "requested bounds"):
            inventory(self.payload, "2026-11-02", self.bounds[1])
        self.payload["data"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            inventory(self.payload, *self.bounds)
