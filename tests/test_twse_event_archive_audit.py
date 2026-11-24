import json
import tempfile
import unittest
from pathlib import Path
from scripts.twse_event_archive_audit import inspect_archive


class ArchiveAuditTests(unittest.TestCase):
    def test_records_fields_without_approving(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / "2026-01.json").write_text(
                json.dumps({"stat": "OK", "fields": ["日期", "代號"], "data": [["115/01/01", "2330"]]}),
                encoding="utf-8")
            (p / "manifest.json").write_text(json.dumps({"entries": [
                {"month": "2026-01", "status": "downloaded_unverified", "file": "2026-01.json"}]}),
                encoding="utf-8")
            result = inspect_archive(p)
            self.assertEqual(result["months"][0]["layouts"][0]["fields"], ["日期", "代號"])
            self.assertFalse(result["schema_approved"])
            self.assertFalse(result["score_eligible"])


if __name__ == "__main__":
    unittest.main()
