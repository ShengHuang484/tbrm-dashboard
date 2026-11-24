import unittest
from scripts.corporate_action_coverage import coverage_audit


class CoverageTests(unittest.TestCase):
    def test_missing_month_blocks(self):
        report = coverage_audit([], "2025-11-01", "2026-11-20",
                                ["2025-11", "2025-12"], ["2025-11"])
        self.assertEqual(report["missing_months"], ["2025-12"])
        self.assertFalse(report["score_eligible"])

    def test_all_requests_still_not_full_verification(self):
        report = coverage_audit([], "2025-11-01", "2025-11-30",
                                ["2025-11"], ["2025-11"])
        self.assertTrue(report["request_coverage_complete"])
        self.assertFalse(report["corporate_action_completeness_verified"])
        self.assertFalse(report["score_eligible"])

    def test_outside_window(self):
        report = coverage_audit([{"ex_date": "2025-10-01"}],
                                "2025-11-01", "2025-11-30", ["2025-11"], ["2025-11"])
        self.assertFalse(report["request_coverage_complete"])


if __name__ == "__main__":
    unittest.main()
