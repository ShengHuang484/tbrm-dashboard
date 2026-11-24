import unittest
from scripts.twse_corporate_action_parser import parse_result_rows, roc_date

URL = "https://www.twse.com.tw/exchangeReport/TWT49U?response=html"


def row(**kwargs):
    d = {"資料日期": "115年11月20日", "股票代號": "4562",
         "除權息前收盤價": "25.65", "除權息參考價": "25.30", "權/息": "權"}
    d.update(kwargs)
    return d


class TWSEParserTests(unittest.TestCase):
    def test_roc_date(self):
        self.assertEqual(roc_date("115年11月20日"), "2026-11-20")

    def test_official_example_is_candidate_not_verified(self):
        events = parse_result_rows([row()], URL)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "4562")
        self.assertEqual(events[0]["reference_price"], "25.30")
        self.assertFalse(events[0]["verified"])

    def test_exclude_etf(self):
        self.assertEqual(parse_result_rows([row(股票代號="0051")], URL), [])

    def test_reject_schema_drift(self):
        with self.assertRaises(ValueError):
            parse_result_rows([{"股票代號": "4562"}], URL)

    def test_reject_untrusted_source(self):
        with self.assertRaises(ValueError):
            parse_result_rows([row()], "https://example.com")

    def test_reject_bad_prices(self):
        with self.assertRaises(ValueError):
            parse_result_rows([row(除權息參考價="0")], URL)


if __name__ == "__main__":
    unittest.main()
