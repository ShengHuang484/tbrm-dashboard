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

    def test_missing_and_duplicate_calendar_dates_are_named(self):
        quotes, calendar, listings = self.csv
        with self.assertRaisesRegex(ValueError, "duplicate calendar dates: 2026-11-19"):
            inspect(self.report, self.metadata, quotes, calendar + b"2026-11-19\n", listings)
        with self.assertRaisesRegex(ValueError, "missing=.*2026-11-19"):
            inspect(self.report, self.metadata, quotes,
                    b"date\n2026-11-20\n", listings)

    def test_both_bases_and_vendor_action_sample(self):
        report = json.loads(json.dumps(self.report).replace("1101", "1312"))
        quotes, calendar, listings = self.csv
        quotes, listings = (data.replace(b"1101", b"1312") for data in (quotes, listings))
        other = json.loads(json.dumps(report))
        other["rights_basis"] = "zero-rights"
        other["sessions"][0]["adjusted_low_codes"] = ["1312"]
        days = report["market_dates"]
        report["applied_events"] = [dict(code="1312", ex_date=days[1], reference_price="30")]
        other["applied_events"] = [dict(code="1312", ex_date=days[1], reference_price="32")]
        history = {days[0]: {"1312": "30"}, days[1]: {"1312": "29"}}
        case = dict(code="1312", before_date=days[0], effective_date=days[1], action="rights_issue",
                    evidence_url="https://example.com/announcement")
        result = inspect(report, self.metadata, quotes, calendar, listings, alternative=other,
                         history=history, event_cases=[case])
        self.assertEqual(result["alternative_basis_diagnostic"]["sessions"][0]["external_only_low_codes"], [])
        self.assertEqual(result["event_price_checks"][0]["status"], "within_display_precision")
        self.assertEqual(result["alternative_event_price_checks"][0]["status"], "price_basis_difference")
        self.assertIn("merger", result["event_types_without_sample"])
        self.assertFalse(result["market_baseline_verified"])
