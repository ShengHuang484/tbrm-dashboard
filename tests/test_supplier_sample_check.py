import hashlib
import json
import unittest
from pathlib import Path

from scripts.supplier_sample_check import FILES, verify

EXAMPLE = Path(__file__).resolve().parents[1] / "research" / "examples" / "supplier_sample"


class SupplierSampleTest(unittest.TestCase):
    def setUp(self):
        self.files = {name: (EXAMPLE / f"{name}.csv").read_bytes() for name in FILES}
        self.metadata = json.loads((EXAMPLE / "manifest.json").read_bytes())
        self.files["roster"] = self.files["roster"].replace(b"TW0002884004", b"KYG000000004")
        roster_sha256 = self.seal("roster")
        self.reference = dict(members=2, canonical_roster_sha256=roster_sha256)

    def seal(self, name):
        digest = hashlib.sha256(self.files[name]).hexdigest()
        self.metadata["sha256"][name] = digest
        return digest

    def test_synthetic_pass_keeps_independence_and_scoring_unverified(self):
        result = verify(self.metadata, self.files, self.reference)
        self.assertEqual(result["intake_status"], "PASS")
        self.assertEqual(result["origin"], "synthetic")
        self.assertEqual(result["license_and_independence_review"], "REVIEW")
        self.assertFalse(result["historical_market_verified"])
        self.assertFalse(result["score_eligible"])

    def test_roster_identity_change_fails_at_equal_count_after_new_delivery_hash(self):
        self.files["roster"] = self.files["roster"].replace(b"KYG000000004", b"KYG000000005")
        with self.assertRaisesRegex(ValueError, "delivery SHA-256"):
            verify(self.metadata, self.files, self.reference)
        self.seal("roster")
        with self.assertRaisesRegex(ValueError, "identity digest"):
            verify(self.metadata, self.files, self.reference)

    def test_copied_alternative_prices_and_quotes_on_suspended_day_fail(self):
        self.files["rights"] = self.files["rights"].replace(b"13.4000", b"13.2000")
        self.seal("rights")
        with self.assertRaisesRegex(ValueError, "dual adjustment factor"):
            verify(self.metadata, self.files, self.reference)
        self.files["rights"] = (EXAMPLE / "rights.csv").read_bytes()
        self.seal("rights")
        self.files["lifecycle"] = self.files["lifecycle"].replace(b"suspended,,,,", b"suspended,9.70,9.7000,,")
        self.seal("lifecycle")
        with self.assertRaisesRegex(ValueError, "nontrading lifecycle row"):
            verify(self.metadata, self.files, self.reference)

    def test_missing_replay_permission_fails(self):
        self.metadata["permissions"]["replay"] = False
        with self.assertRaisesRegex(ValueError, "replay permissions"):
            verify(self.metadata, self.files, self.reference)

    def test_invalid_manifest_field_types_fail_validation(self):
        for field, value, message in (
            ("supplier", 1312, "missing source"),
            ("permissions", ["replay"], "replay permissions"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                verify(dict(self.metadata, **{field: value}), self.files, self.reference)
