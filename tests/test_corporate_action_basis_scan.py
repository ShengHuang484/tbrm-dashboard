import unittest

from scripts.corporate_action_basis_scan import FIELDS, scan_rows


class BasisScanTest(unittest.TestCase):
    def test_records_preferred_share_without_expanding_ordinary_scope(self):
        day = "2026-06-11"
        raw = [["115/06/11", code, "權", "13.20", "13.40", "13.20", "13.20"]
               for code in ("1312", "1312A")]
        reports = {"2026-06": (dict(stat="OK", fields=FIELDS, data=raw), "https://www.twse.com.tw/report")}
        listings = [dict(code="1312", listed_from=day, delisted_on=None)]
        result, counts = scan_rows(reports, [day], listings)
        self.assertEqual([row["scope"] for row in result], ["reconstructed_ordinary", "outside_reconstructed_scope"])
        self.assertTrue(all(row["theoretical_uplift"] for row in result))
        self.assertEqual(sum(counts.values()), 2)
        raw.append(raw[0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            scan_rows(reports, [day], listings)
