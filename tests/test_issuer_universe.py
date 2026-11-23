import json
import unittest

from scripts.issuer_universe import reconcile, snapshot


class IssuerScopeTests(unittest.TestCase):
    def test_tdr_filter_retains_historical_only_code_and_pre_listing_identity(self):
        days = ["2026-01-02", "2026-01-05", "2026-01-06"]
        history = {d: {"9105": 5, "1101": 20, "3454": 30} for d in days}
        rows = [dict(code="9105", listed_from=days[-1], industry="91"),
                dict(code="1101", listed_from=days[0], industry="01")]
        result = reconcile(history, [], rows, days[-1], 1)
        self.assertEqual(result["history_only_codes"], ["3454"])
        self.assertEqual(result["quotes_before_snapshot_listing"], {"9105": days[0]})
        self.assertEqual([r["strict_eligible_count"] for r in result["sessions"]], [3, 2])

    def test_snapshot_rejects_duplicate_codes_and_conflicting_security_type(self):
        row = {"公司代號": "9103", "公司簡稱": "example-DR", "產業別": "91",
               "上市日期": "20020524", "出表日期": "1151122"}
        raw = lambda rows: json.dumps(rows).encode()
        self.assertEqual(snapshot(raw([row]))[1]["snapshot_date"], "2026-11-22")
        for invalid in ([row, row], [dict(row, 產業別="01")]):
            with self.assertRaises(ValueError):
                snapshot(raw(invalid))
