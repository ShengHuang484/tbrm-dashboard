import json
import unittest
from pathlib import Path

from scripts.external_delivery_check import inspect


class ExternalDeliveryTests(unittest.TestCase):
    def setUp(self):
        root = Path("research/examples/external_delivery")
        self.report = json.loads((root / "report.json").read_text())
        self.metadata = json.loads((root / "metadata.json").read_text())
        self.csv = [(root / name).read_bytes() for name in ("quotes.csv", "calendar.csv", "listings.csv")]

    def test_vendor_low_is_classified_without_activating_score(self):
        result = inspect(self.report, self.metadata, *self.csv)
        [day] = result["comparison"]["sessions"]
        self.assertEqual(day["disagreement_by_code"], {"1101": ["external_low_only"]})
        self.assertEqual(result["listing_disagreement"], [])
        self.assertFalse(result["score_eligible"])

    def test_missing_historical_listing_is_reported_even_if_never_eligible(self):
        quotes, calendar, listings = self.csv
        result = inspect(self.report, self.metadata, quotes, calendar, listings.splitlines()[0]
                         + b"\n1101,2000-01-01,\n")
        self.assertEqual(result["listing_disagreement"][0]["local_only"], ["1102"])

    def test_invalid_currency_or_rights_basis_stops_review(self):
        for changes in (dict(currency="USD"), dict(rights_basis="zero-rights"),
                        dict(price_decimal_places=1)):
            with self.assertRaises(ValueError):
                inspect(self.report, dict(self.metadata, **changes), *self.csv)
