import unittest

from scripts.twse_ex_right_date_audit import evaluate, implied_auction_base


class EffectiveDateAuditTest(unittest.TestCase):
    def test_preserves_no_comparison_without_promoting_missing_event(self):
        quotes = {"date": "20260713", "stat": "OK", "tables": [{
            "fields": ["證券代號", "收盤價", "漲跌(+/-)", "漲跌價差"],
            "data": [["2008", "29.30", "<span>X</span>", "0.00"]],
        }]}
        events = {"stat": "OK", "strDate": "20260713", "endDate": "20260713",
                  "fields": ["股票代號", "資料日期", "除權息前收盤價", "除權息參考價", "開盤競價基準"],
                  "data": []}
        [result] = evaluate("2026-07-13", [{"code": "2008"}], quotes, events)
        self.assertEqual(result["quote"]["漲跌(+/-)"], "X")
        self.assertIsNone(result["dated_event"])
        self.assertFalse(result["score_eligible"])
        with self.assertRaisesRegex(ValueError, "bounds mismatch"):
            evaluate("2026-07-13", [{"code": "2008"}], quotes, dict(events, strDate="20260710"))

    def test_numeric_basis_requires_sign_or_zero_change(self):
        quote = {"收盤價": "37.25", "漲跌(+/-)": "-", "漲跌價差": "0.15"}
        self.assertEqual(str(implied_auction_base(quote)), "37.40")
        self.assertIsNone(implied_auction_base(dict(quote, **{"漲跌(+/-)": ""})))
        self.assertEqual(str(implied_auction_base(
            dict(quote, **{"漲跌(+/-)": "", "漲跌價差": "0.00"}))), "37.25")
