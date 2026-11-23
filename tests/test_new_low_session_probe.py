import json
import unittest

from scripts.new_low_session_probe import evidence_report, ordinary_isin_prefix, scoped_isins


class SessionProbeTest(unittest.TestCase):
    day = "2026-11-23"

    @staticmethod
    def payload(obj):
        return json.dumps(obj, ensure_ascii=False).encode()

    def html(self):
        def row(*cells):
            return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"
        return ("最近更新日期:2026/11/23  </center>" + row("股票")
                + row("1538　正峰", "TW0001538007", "2002/08/26", "上市", "機械", "ESVUFR", "")
                + row("上市認購(售)權證")).encode("cp950")

    def test_board_parser_requires_date_and_end_marker(self):
        roster = ordinary_isin_prefix(self.html(), self.day)
        self.assertEqual(roster["1538"]["security_id"], "TW0001538007")
        with self.assertRaisesRegex(ValueError, "snapshot update date"):
            ordinary_isin_prefix(self.html(), "2026-11-20")
        with self.assertRaisesRegex(ValueError, "whole general-board"):
            ordinary_isin_prefix(self.html().split("上市認購(售)權證".encode("cp950"))[0], self.day)

    def fixture(self):
        sources = {key: self.payload(value) for key, value in {
            "quotes": dict(stat="OK", date="20261123", tables=[
                dict(fields=["證券代號", "收盤價"], data=[["1538", "--"], ["1808", "34.85"]])]),
            "tib": dict(stat="OK", date="20261123", tables=[
                dict(title="115年11月23日 每日收盤行情(創新板股票)",
                     fields=["證券代號", "收盤價"], data=[["1808", "34.85"]])]),
            "calendar": dict(stat="OK", data=[["115/11/20"], ["115/11/23"]]),
            "reduction": dict(stat="OK", strDate="20261123", endDate="20261123",
                              fields=["股票代號", "恢復買賣日期", "停止買賣前收盤價格", "恢復買賣參考價"],
                              data=[["1808", "115/11/23", "31.00", "36.25"]]),
            "ex_right": dict(stat="很抱歉，沒有符合條件的資料!"),
            "stock_1538": dict(stat="OK", date="20261101", title="115年11月 1538 正峰",
                              fields=["日期", "成交股數", "成交筆數", "收盤價"],
                              data=[["115/11/23", "2", "2", "--"]]),
        }.items()}
        sources["isin_prefix"] = self.html()
        checkpoint = self.payload(dict(history={"2026-11-20": {"1808": 31}},
                                       lookback=252, seed_input_sha256={}, listing_intervals=[
            dict(code=code, listed_from="2000-01-01", delisted_on=None) for code in ("1538", "1808")]))
        return checkpoint, sources

    def test_partial_session_reports_real_advance_gate_and_omits_counts(self):
        checkpoint, sources = self.fixture()
        result = evidence_report(self.day, checkpoint, sources)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["confirmed_gap_reasons"], {"1538": "activity_without_close"})
        self.assertEqual(result["innovation_board_trade_table_codes"], ["1808"])
        self.assertEqual(result["quoted_codes_outside_observed_boards"], [])
        self.assertEqual(result["reduction_observations"][0]["exchange_reference"], "36.25")
        self.assertNotIn("report", result)
        self.assertNotIn("checkpoint", result)
        self.assertFalse(result["score_eligible"])

    def test_complete_current_scope_reaches_unreviewed_actions_gate(self):
        checkpoint, sources = self.fixture()

        def roster(isin, code, market, kind, cfi):
            header = ["頁面編號", "國際證券編碼", "有價證券代號", "有價證券名稱", "市場別", "有價證券別",
                      "產業別", "公開發行/上市(櫃)/發行日", "CFICode", "備註"]
            data = ["1", isin, code, "測試", market, kind, "", "2000/01/01", cfi, ""]
            return "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
                           for row in (header, data)).encode("cp950")

        quote = json.loads(sources["quotes"])
        quote["tables"][0]["data"].append(["9103", "2.00"])
        sources["quotes"] = self.payload(quote)
        sources["tib_isin"] = roster("TW0001808004", "1808", "上市臺灣創新板", "創新板", "ESVUFR")
        sources["tdr_isin"] = roster("TW0009103002", "9103", "上市", "臺灣存託憑證(TDR)", "EDSDDR")
        result = evidence_report(self.day, checkpoint, sources, identity_retrieved_on=self.day)
        scoped = result["scoped_identity_evidence"]
        self.assertEqual(scoped["same_source_ordinary_member_count"], 2)
        self.assertEqual(scoped["tdr_exclusions"], {"9103": "TW0009103002"})
        self.assertEqual(result["replay_error"], "session action evidence is incomplete")
        self.assertIn("listing-start", result["blocked_inputs"][1])
        self.assertFalse(scoped["independent_membership_verified"])
        with self.assertRaisesRegex(ValueError, "same-day capture"):
            evidence_report(self.day, checkpoint, sources, identity_retrieved_on="2026-11-20")
        with self.assertRaisesRegex(ValueError, "invalid scoped ISIN"):
            scoped_isins(sources["tdr_isin"], "上市臺灣創新板", "創新板", "ES")
