import unittest
from scripts.twse_quote_gap_crosscheck import crosscheck, stock_rows


class QuoteGapTests(unittest.TestCase):
    def test_parses_official_stock_detail(self):
        payload = {"tables": [{"fields": ["證券代號", "證券名稱", "收盤價"],
                               "data": [["2330", "台積電", "100"], ["2317", "鴻海", "--"]]}]}
        self.assertEqual(stock_rows(payload), {"2330": "100", "2317": "--"})

    def test_detects_quote_present_in_official_report(self):
        audit = {"internal_gap_details": [
            {"code": "2330", "internal_missing_dates": ["2026-01-05"]},
            {"code": "2317", "internal_missing_dates": ["2026-01-05"]},
        ]}
        def fetcher(url):
            return {"stat": "OK", "date": "20260105",
                    "tables": [{"fields": ["證券代號", "收盤價"],
                                "data": [["2330", "100"], ["2317", "--"]]}]}
        report = crosscheck({}, audit, fetcher)
        self.assertEqual(report["archive_missing_but_official_quote_present"], 1)
        self.assertEqual(report["checks"][1]["status"], "official_quote_present_missing_in_archive")
        self.assertFalse(report["score_eligible"])

    def test_pagination_does_not_repeat_dates(self):
        audit = {"internal_gap_details": [
            {"code": "2330", "internal_missing_dates": ["2026-01-05", "2026-01-06", "2026-01-07"]}
        ]}
        def fetcher(url):
            return {"stat": "OK", "tables": [{"fields": ["證券代號", "收盤價"],
                    "data": [["2330", "--"]]}]}
        first = crosscheck({}, audit, fetcher, max_dates=2, offset=0)
        second = crosscheck({}, audit, fetcher, max_dates=2, offset=2)
        self.assertEqual(first["next_offset"], 2)
        self.assertIsNone(second["next_offset"])
        self.assertFalse(set(first["checked_dates"]) & set(second["checked_dates"]))

    def test_unavailable_source_is_not_misclassified_as_no_trade(self):
        audit = {"internal_gap_details": [{"code": "2330", "internal_missing_dates": ["2026-01-05"]}]}
        def fetcher(url):
            raise OSError("unavailable")
        report = crosscheck({}, audit, fetcher)
        self.assertEqual(report["official_source_unavailable"], 1)
        self.assertFalse(report["all_gaps_verified"])


if __name__ == "__main__":
    unittest.main()
