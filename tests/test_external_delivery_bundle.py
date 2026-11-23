import hashlib
import json
import unittest
from pathlib import Path

from scripts.external_delivery_bundle import review


class DeliveryBundleTest(unittest.TestCase):
    def setUp(self):
        root = Path("research/examples/external_delivery")
        self.report = json.loads((root / "report.json").read_text())
        self.metadata = json.loads((root / "metadata.json").read_text())
        self.metadata.update(origin="synthetic", adjustment_anchor_date="2026-11-20",
                             upstream_source="synthetic fixture", usage_limits="test only")
        self.metadata["corporate_action_rules"].update(face_value_change="fixture", share_conversion="fixture")
        self.files = {name: (root / f"{name}.csv").read_bytes() for name in ("quotes", "calendar")}
        self.files.update(
            listings=(b"code,listed_from,delisted_on,security_id\n1101,2000-01-01,,S1\n"
                      b"1102,2000-01-01,2026-11-20,S2\n"),
            roster=(b"date,code,security_id\n2026-11-19,1101,S1\n2026-11-19,1102,S2\n2026-11-20,1101,S1\n"),
            trading_status=b"date,code,reason,source_url\n",
            events=(b"date,code,event_type,successor_code,source_url\n"
                    b"2026-11-20,1101,reverse_split,,https://example.com/split\n"
                    b"2026-11-20,1102,merger,1101,https://example.com/merger\n"))
        self.report["applied_events"] = [
            dict(code="1101", ex_date="2026-11-20", reference_price="60", event_type="reverse_split")]
        self.history = {"2026-11-19": {"1101": "30", "1102": "21"}, "2026-11-20": {"1101": "58"}}
        self.cases = [dict(action="reverse_split", code="1101", before_date="2026-11-19",
                           effective_date="2026-11-20", evidence_url="https://example.com/split")]

    def run_bundle(self, rehash=True):
        if rehash:
            self.metadata["bundle_sha256"] = {k: hashlib.sha256(raw).hexdigest() for k, raw in self.files.items()}
        return review(self.report, self.metadata, self.files, history=self.history, alternative=None,
                      event_cases=self.cases, local_gaps={"groups": []})

    def test_reverse_split_return_and_merger_are_distinct(self):
        result = self.run_bundle()
        self.assertEqual(result["origin"], "synthetic")
        row, = result["action_inventory_review"]
        self.assertEqual(row["vendor_events"][0]["successor_code"], "1101")
        self.assertEqual(result["roster"]["sessions"][-1]["adjacent_changes"]["exited"], ["1102"])
        sample, = result["quote_and_low_comparison"]["event_price_checks"]
        self.assertEqual(sample["status"], "within_display_precision")
        self.assertFalse(result["market_baseline_verified"])

    def test_hash_anchor_and_identity_conflict(self):
        self.run_bundle()
        self.files["roster"] = self.files["roster"].replace(b"1102,S2", b"1102,S3")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.run_bundle(rehash=False)
        with self.assertRaisesRegex(ValueError, "listing intervals conflict"):
            self.run_bundle()
        self.metadata["adjustment_anchor_date"] = "2026-11-19"
        with self.assertRaisesRegex(ValueError, "anchor"):
            self.run_bundle()

    def test_missing_close_status_must_not_overlap_a_quote(self):
        self.files["trading_status"] += b"2026-11-20,1101,announced_stop,https://example.com/status\n"
        with self.assertRaisesRegex(ValueError, "quoted stock"):
            self.run_bundle()
