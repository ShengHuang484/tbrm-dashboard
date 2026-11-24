import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from scripts.twse_event_download import archive, months_between, fetch_month


class EventDownloadTests(unittest.TestCase):
    def test_month_boundary(self):
        self.assertEqual(list(months_between("2025-12", "2026-02")),
                         ["2025-12", "2026-01", "2026-02"])

    def test_archive_never_verifies(self):
        def fake(month):
            payload = {"stat": "OK", "fields": ["資料日期", "股票代號"],
                       "data": [[month.replace("-", "") + "05", "2330"]]}
            raw = json.dumps(payload).encode()
            return "https://www.twse.com.tw/example", raw, payload
        with tempfile.TemporaryDirectory() as tmp:
            result = archive("2026-01", "2026-02", tmp, fetcher=fake)
            self.assertEqual(len(result["successful_months"]), 2)
            self.assertFalse(result["score_eligible"])
            self.assertFalse(result["corporate_action_completeness_verified"])
            self.assertTrue((Path(tmp) / "2026-01.json").exists())

    def test_rejects_wrong_month_events(self):
        def fake(month):
            payload = {"stat": "OK", "fields": ["資料日期", "股票代號"],
                       "data": [["20260205", "2330"]]}
            return "https://www.twse.com.tw/example", json.dumps(payload).encode(), payload
        with tempfile.TemporaryDirectory() as tmp:
            result = archive("2026-01", "2026-01", tmp, fetcher=fake)
            self.assertEqual(result["failed_months"], ["2026-01"])
            self.assertFalse((Path(tmp) / "2026-01.json").exists())

    def test_accepts_chinese_roc_date(self):
        def fake(month):
            payload = {"stat": "OK", "fields": ["資料日期", "股票代號"],
                       "data": [["115年11月20日", "2330"]]}
            return "https://www.twse.com.tw/example", json.dumps(payload).encode(), payload
        with tempfile.TemporaryDirectory() as tmp:
            result = archive("2026-11", "2026-11", tmp, fetcher=fake)
            self.assertEqual(result["successful_months"], ["2026-11"])
            self.assertEqual(result["entries"][0]["first_event_date"], "20261120")
            self.assertFalse(result["score_eligible"])

    def test_fetch_month_uses_explicit_historical_range(self):
        captured = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return b'{"stat":"OK","data":[]}'
        def opener(request, timeout):
            captured.append(request.full_url)
            return Response()
        fetch_month("2025-11", opener=opener)
        url = urlparse(captured[0])
        params = parse_qs(url.query)
        self.assertEqual(params["startDate"], ["20251101"])
        self.assertEqual(params["endDate"], ["20251130"])
        self.assertIn("/rwd/zh/exRight/TWT49U", url.path)

    def test_empty_payload_does_not_prove_month_coverage(self):
        def fake(month):
            payload = {"stat": "OK", "fields": ["資料日期"], "data": []}
            return "https://www.twse.com.tw/example", json.dumps(payload).encode(), payload
        with tempfile.TemporaryDirectory() as tmp:
            result = archive("2025-11", "2025-11", tmp, fetcher=fake)
            self.assertEqual(result["failed_months"], ["2025-11"])
            self.assertFalse(result["score_eligible"])

    def test_partial_failure_recorded(self):
        def failing(month):
            raise ValueError("network failure")
        with tempfile.TemporaryDirectory() as tmp:
            result = archive("2026-01", "2026-01", tmp, fetcher=failing)
            self.assertEqual(result["failed_months"], ["2026-01"])
            self.assertFalse(result["score_eligible"])


if __name__ == "__main__":
    unittest.main()
