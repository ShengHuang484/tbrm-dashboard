import hashlib
from copy import deepcopy
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

    def run_bundle(self, rehash=True, alternative=None):
        if rehash:
            self.metadata["bundle_sha256"] = {k: hashlib.sha256(raw).hexdigest() for k, raw in self.files.items()}
        return review(self.report, self.metadata, self.files, history=self.history, alternative=alternative,
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

    def test_unclassified_vendor_gap_has_explicit_blocker(self):
        self.files["quotes"] = self.files["quotes"].replace(b"2026-11-19,1102,21.00\n", b"")
        result = self.run_bundle()
        self.assertEqual(result["intake_status"], "BLOCKED")
        self.assertEqual(result["intake_blockers"]["unresolved_vendor_gap_pairs"], 1)
        self.assertEqual(result["gap_differences"][0]["unresolved_vendor_codes"], ["1102"])
        self.assertEqual(result["independence_review"], "synthetic_only")
        self.assertFalse(result["market_baseline_verified"])

    def test_synthetic_bundle_replays_alternative_rights_basis_with_other_events(self):
        self.report["listing_intervals"].append(dict(code="1312", listed_from="2000-01-01", delisted_on=None))
        self.report["sessions"][0]["eligible_codes"].append("1312")
        self.report["applied_events"].append(dict(code="1312", ex_date="2026-11-20",
                                                  reference_price="13.40", event_type="rights_issue"))
        self.files["listings"] += b"1312,2000-01-01,,S3\n"
        self.files["roster"] += b"2026-11-19,1312,S3\n2026-11-20,1312,S3\n"
        self.files["quotes"] += b"2026-11-19,1312,13.40\n2026-11-20,1312,12.80\n"
        self.files["events"] += b"2026-11-20,1312,rights_issue,,https://example.com/rights\n"
        self.history["2026-11-19"]["1312"] = "13.20"
        self.history["2026-11-20"]["1312"] = "12.80"
        self.cases.append(dict(action="rights_issue", code="1312", before_date="2026-11-19",
                               effective_date="2026-11-20", evidence_url="https://example.com/rights"))
        alternative = deepcopy(self.report)
        alternative["rights_basis"] = "zero-rights"
        alternative["applied_events"][-1]["reference_price"] = "13.20"
        alternative["sessions"][0]["adjusted_low_codes"] = ["1312"]
        result = self.run_bundle(alternative=alternative)["quote_and_low_comparison"]
        self.assertEqual(result["event_price_checks"][-1]["status"], "within_display_precision")
        self.assertEqual(result["alternative_event_price_checks"][-1]["status"], "price_basis_difference")
        self.assertEqual(result["alternative_basis_diagnostic"]["sessions"][0]["local_low_count_on_comparable"], 1)
