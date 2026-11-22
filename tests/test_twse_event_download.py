import json
import tempfile
import unittest
from pathlib import Path
from scripts.twse_event_download import archive, months_between


class EventDownloadTests(unittest.TestCase):
    def test_month_boundary(self):
        self.assertEqual(list(months_between("2025-12", "2026-02")),
                         ["2025-12", "2026-01", "2026-02"])

    def test_archive_never_verifies(self):
        def fake(month):
            raw = json.dumps({"stat": "OK", "data": []}).encode()
            return "https://www.twse.com.tw/example", raw, {"stat": "OK", "data": []}
        with tempfile.TemporaryDirectory() as tmp:
            result = archive("2026-01", "2026-02", tmp, fetcher=fake)
            self.assertEqual(len(result["successful_months"]), 2)
            self.assertFalse(result["score_eligible"])
            self.assertFalse(result["corporate_action_completeness_verified"])
            self.assertTrue((Path(tmp) / "2026-01.json").exists())

    def test_partial_failure_recorded(self):
        def failing(month):
            raise ValueError("network failure")
        with tempfile.TemporaryDirectory() as tmp:
            result = archive("2026-01", "2026-01", tmp, fetcher=failing)
            self.assertEqual(result["failed_months"], ["2026-01"])
            self.assertFalse(result["score_eligible"])


if __name__ == "__main__":
    unittest.main()
