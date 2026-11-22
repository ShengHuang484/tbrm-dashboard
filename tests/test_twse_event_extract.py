import unittest
from scripts.twse_event_extract import extract_candidates

URL = "https://www.twse.com.tw/exchangeReport/TWT49U?response=json"
FIELDS = ["除權息日期", "股票代號", "除權息前收盤價", "除權息參考價", "權/息"]
ROW = ["115/11/20", "2330", "100", "95", "息"]


class ExtractTests(unittest.TestCase):
    def test_flat_table(self):
        e = extract_candidates({"stat": "OK", "fields": FIELDS, "data": [ROW]}, URL)
        self.assertEqual(e[0]["ex_date"], "2026-11-20")
        self.assertFalse(e[0]["verified"])

    def test_nested_tables(self):
        e = extract_candidates({"stat": "OK", "tables": [{"fields": FIELDS, "data": [ROW]}]}, URL)
        self.assertEqual(len(e), 1)

    def test_missing_column_fails(self):
        with self.assertRaises(ValueError):
            extract_candidates({"stat": "OK", "fields": FIELDS[:-1], "data": [ROW[:-1]]}, URL)

    def test_bad_row_length_fails(self):
        with self.assertRaises(ValueError):
            extract_candidates({"stat": "OK", "fields": FIELDS, "data": [ROW[:-1]]}, URL)

    def test_non_ok_fails(self):
        with self.assertRaises(ValueError):
            extract_candidates({"stat": "查無資料", "fields": FIELDS, "data": [ROW]}, URL)


if __name__ == "__main__":
    unittest.main()
