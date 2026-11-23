import unittest

from scripts.new_low_baseline import compare
from scripts.new_low_baseline_import import normalize


class BaselineImportTest(unittest.TestCase):
    metadata = dict(provider="fixture", source_url="https://example.com",
                    adjustment_method="corporate action adjusted", data_origin="provider_adjusted_close",
                    usage_basis="test fixture")
    calendar = b"date\n2026-01-02\n2026-01-05\n"
    quotes = b"date,code,adjusted_close\n2026-01-02,1101,25\n2026-01-05,1101,24\n"
    listings = b"code,listed_from,delisted_on\n1101,2026-01-02,\n"

    def test_import_provenance_and_bidirectional_cohort_diff(self):
        baseline = normalize(self.metadata, self.quotes, self.calendar, self.listings)
        self.assertEqual(len(baseline["sha256"]["quotes"]), 64)
        result = compare({
            "market_dates": baseline["market_dates"], "lookback": 1,
            "sessions": [{"date": "2026-01-05", "eligible_codes": ["1102"],
                          "adjusted_low_codes": ["1102"]}],
        }, baseline)
        [row] = result["sessions"]
        self.assertEqual(row["external_only_eligible_codes"], ["1101"])
        self.assertEqual(row["local_only_eligible_codes"], ["1102"])
        self.assertEqual(row["external_low_count"], 1)
        self.assertEqual(row["comparable"], 0)
        self.assertFalse(result["market_baseline_verified"])

    def test_rejects_duplicates_and_locally_rebuilt_prices(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            normalize(self.metadata, self.quotes + b"2026-01-05,1101,23\n", self.calendar)
        with self.assertRaisesRegex(ValueError, "provider-adjusted"):
            normalize(dict(self.metadata, data_origin="local_rebuild"), self.quotes, self.calendar)
