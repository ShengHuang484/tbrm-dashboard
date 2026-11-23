import json
import unittest
from pathlib import Path

from scripts.corporate_action_identity_review import audit_identity_evidence


class IdentityEvidenceTest(unittest.TestCase):
    def test_archive_review_distinguishes_parent_and_predecessor(self):
        history = json.loads(Path("data/history/new_low_closes.json").read_text())
        evidence = json.loads(Path("research/share_identity_evidence.json").read_text())
        report = audit_identity_evidence(history, evidence)
        survivor, subsidiary, exchange = report["records"]
        self.assertIsNotNone(survivor["first_at_or_after_reference_quote"])
        self.assertIsNotNone(subsidiary["first_at_or_after_reference_quote"])
        self.assertFalse(exchange["predecessor_boundary_conflict"])
        self.assertTrue(exchange["successor_already_quoted"])
        self.assertTrue(all(r["factor"] is None for r in report["records"]))
        self.assertFalse(report["score_eligible"])

    def test_exchange_on_boundary_flags_conflict_without_emitting_factor(self):
        evidence = json.loads(Path("research/share_identity_evidence.json").read_text())[-1:]
        report = audit_identity_evidence({
            "2026-08-31": {"2867": 9, "2884": 30},
            "2026-09-01": {"2867": 9, "2884": 30},
        }, evidence)
        self.assertTrue(report["records"][0]["predecessor_boundary_conflict"])
        self.assertIsNone(report["records"][0]["factor"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit_identity_evidence({"2026-09-01": {"2867": 9}}, evidence * 2)
