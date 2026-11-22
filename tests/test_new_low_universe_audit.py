import unittest
from scripts.new_low_universe_audit import audit_history


class UniverseAuditTests(unittest.TestCase):
    def test_distinguishes_internal_from_boundary_gaps(self):
        dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
        history = {
            dates[0]: {"2330": "100", "2317": "90"},
            dates[1]: {"2330": "101", "1101": "40"},
            dates[2]: {"2330": "102", "2317": "91", "1101": "41"},
            dates[3]: {"2330": "103", "1101": "42"},
        }
        report = audit_history(history, required_days=4)
        self.assertEqual(report["full_window_codes"], 1)
        self.assertEqual(report["variable_coverage_codes"], 2)
        self.assertEqual(report["internal_gap_code_count"], 1)
        self.assertEqual(report["boundary_only_code_count"], 1)
        self.assertEqual(report["internal_gap_details"][0]["code"], "2317")
        self.assertEqual(report["internal_gap_details"][0]["internal_missing_days"], 1)
        self.assertFalse(report["score_eligible"])

    def test_invalid_price_blocks(self):
        history = {"2026-01-02": {"2330": "0"}}
        report = audit_history(history, required_days=1)
        self.assertFalse(report["raw_history_structurally_valid"])
        self.assertEqual(report["invalid_close_count"], 1)


if __name__ == "__main__":
    unittest.main()
