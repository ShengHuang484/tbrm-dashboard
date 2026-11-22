import unittest
from scripts.twse_gap_aggregate import aggregate


class AggregateTests(unittest.TestCase):
    def test_nonoverlapping_batches(self):
        a = {"checked_dates": ["2026-01-05"], "checks": [
            {"date": "2026-01-05", "status": "official_row_no_valid_close"}]}
        b = {"checked_dates": ["2026-01-06"], "checks": [
            {"date": "2026-01-06", "status": "not_found_in_official_detail"}]}
        result = aggregate([a, b], 3)
        self.assertEqual(result["dates_remaining"], 1)
        self.assertEqual(result["stock_date_pairs_checked"], 2)
        self.assertFalse(result["score_eligible"])

    def test_duplicate_date_is_rejected(self):
        report = {"checked_dates": ["2026-01-05"], "checks": []}
        with self.assertRaisesRegex(ValueError, "overlapping"):
            aggregate([report, report], 2)


if __name__ == "__main__":
    unittest.main()
