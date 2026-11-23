import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.monthly_ex_right_scenario import load_months, reconcile_months


class MonthlyArchiveTest(unittest.TestCase):
    def test_exact_month_coverage_and_archive_hash(self):
        raw = b'{"stat":"OK","fields":[],"data":[]}'
        entry = {"month": "2026-01", "status": "downloaded_unverified", "file": "rows.json",
                 "source_url": "https://www.twse.com.tw/example", "sha256": hashlib.sha256(raw).hexdigest()}
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.zip"
            with ZipFile(source, "w") as archive:
                archive.writestr("manifest.json", json.dumps({"entries": [entry]}))
                archive.writestr("rows.json", raw)
            self.assertEqual(load_months([source], ["2026-01-02"])[0], [])
            with self.assertRaisesRegex(ValueError, "omit required"):
                load_months([source], ["2026-01-02", "2026-02-02"])
            with ZipFile(source, "w") as archive:
                archive.writestr("manifest.json", json.dumps({"entries": [entry]}))
                archive.writestr("rows.json", raw + b" ")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                load_months([source], ["2026-01-02"])

    def test_reconciles_closed_date_and_preserves_first_session(self):
        h = {"2026-01-02": {"1101": 100}, "2026-01-05": {"1101": 94}}
        close = {"code": "1101", "prior_close": "100", "reference_price": "95"}
        cases = {"cases": [{"code": "1101", "reported_date": "2026-01-03",
                            "prior_close": "100", "reference": "95"}]}
        rows = [dict(close, ex_date=day) for day in ("2026-01-02", "2026-01-03")]
        events, excluded = reconcile_months(h, rows, cases, [dict(close, ex_date="2026-01-05")])
        self.assertEqual(events, [])
        self.assertEqual([r["reason"] for r in excluded],
                         ["first_archive_session", "replaced_by_reconciled_session"])
        events, excluded = reconcile_months(h, [dict(close, ex_date="2026-01-05")], {"cases": []}, [])
        self.assertTrue(events[0]["verified"])
        self.assertEqual(excluded, [])
