import hashlib
import json
import unittest
from pathlib import Path

from scripts.external_delivery_check import inspect
from scripts.new_low_baseline_import import normalize


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
        with self.assertRaisesRegex(ValueError, "extra=.*2026-11-18"):
            inspect(self.report, self.metadata, quotes,
                    b"date\n2026-11-18\n2026-11-19\n2026-11-20\n", listings)

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
        self.assertEqual(result["price_movement_checks"][0]["differences_by_code"], {})
        self.assertEqual(result["alternative_price_movement_checks"][0]["differences_by_code"]
                         ["1312"]["status"], "price_movement_difference")
        self.assertIn("merger", result["event_types_without_sample"])
        self.assertFalse(result["market_baseline_verified"])

    def test_repeated_code_requires_identity_and_is_not_compared_across_boundary(self):
        quotes, calendar, _ = self.csv
        repeated = b"1101,2000-01-01,2026-11-20\n1101,2026-11-20,\n"
        header = b"code,listed_from,delisted_on"
        self.assertEqual(len(normalize(self.metadata, quotes, calendar,
                                      header + b"\n" + repeated)["listings"]), 2)
        with self.assertRaisesRegex(ValueError, "repeated listing codes require security_id: 1101"):
            inspect(self.report, self.metadata, quotes, calendar, header + b"\n" + repeated)
        listings = (header + b",security_id\n1101,2000-01-01,2026-11-20,issuer-original\n"
                    b"1101,2026-11-20,,issuer-reused\n")
        before, after = self.report["market_dates"]
        result = inspect(self.report, self.metadata, quotes, calendar, listings,
                         history={before: {"1101": "30"}, after: {"1101": "29"}})
        self.assertEqual(result["price_movement_checks"][0]["listing_boundaries"], ["1101"])
        self.assertEqual(result["price_movement_checks"][0]["compared"], 0)
        self.assertEqual([r["security_id"] for r in result["vendor_repeated_listing_codes"]["1101"]],
                         ["issuer-original", "issuer-reused"])

    def test_persistent_identity_surfaces_code_changes_and_rejects_overlaps(self):
        quotes, calendar, _ = self.csv
        listings = (b"code,listed_from,delisted_on,security_id\n"
                    b"1102,2000-01-01,2026-11-19,security-original\n"
                    b"1101,2026-11-19,,security-original\n")
        result = inspect(self.report, self.metadata, quotes, calendar, listings)
        transition = result["vendor_security_code_transitions"]["security-original"]
        self.assertEqual([row["code"] for row in transition], ["1102", "1101"])
        with self.assertRaisesRegex(ValueError, "overlapping listing codes for security_id"):
            inspect(self.report, self.metadata, quotes, calendar,
                    listings.replace(b"2000-01-01,2026-11-19", b"2000-01-01,2026-11-20"))

    def test_declared_csv_checksums_match_the_received_bytes(self):
        checksums = {name: hashlib.sha256(raw).hexdigest()
                     for name, raw in zip(("quotes", "calendar", "listings"), self.csv)}
        metadata = dict(self.metadata, file_sha256=checksums)
        result = inspect(self.report, metadata, *self.csv)
        self.assertEqual(result["comparison"]["export_provenance"]["sha256"], checksums)
        checksums["quotes"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "declared delivery SHA-256"):
            inspect(self.report, metadata, *self.csv)
