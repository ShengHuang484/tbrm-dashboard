import json
import unittest
from pathlib import Path

from scripts.corporate_action_identity_review import audit_identity_evidence


class IdentityEvidenceTest(unittest.TestCase):
    def test_archive_review_distinguishes_parent_and_predecessor(self):
        history = json.loads(Path("data/history/new_low_closes.json").read_text())
        evidence = json.loads(Path("research/share_identity_evidence.json").read_text())
        report = audit_identity_evidence(history, evidence)
        by_code = {r["code"]: r for r in report["records"]}
        survivor, subsidiary, exchange = (by_code[c] for c in ("2305", "2887", "2867"))
        self.assertFalse(by_code["3454"]["quoted_during_stop"])
        self.assertEqual(by_code["3454"]["last_pre_reference_quote"], "2026-03-18")
        self.assertIsNone(by_code["3010"]["effective_date"])
        self.assertIsNotNone(survivor["first_at_or_after_reference_quote"])
        self.assertIsNotNone(subsidiary["first_at_or_after_reference_quote"])
        self.assertFalse(exchange["predecessor_boundary_conflict"])
        self.assertTrue(exchange["successor_already_quoted"])
        self.assertTrue(all(r["factor"] is None for r in report["records"]))
        self.assertFalse(report["score_eligible"])

    def test_exchange_on_boundary_flags_conflict_without_emitting_factor(self):
        evidence = [r for r in json.loads(Path("research/share_identity_evidence.json").read_text())
                    if r["code"] == "2867"]
        report = audit_identity_evidence({
            "2026-08-31": {"2867": 9, "2884": 30},
            "2026-09-01": {"2867": 9, "2884": 30},
        }, evidence)
        self.assertTrue(report["records"][0]["predecessor_boundary_conflict"])
        self.assertIsNone(report["records"][0]["factor"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit_identity_evidence({"2026-09-01": {"2867": 9}}, evidence * 2)

    def test_deferred_revision_cannot_certify_the_superseded_date(self):
        records = json.loads(Path("research/share_identity_evidence.json").read_text())
        row = next(r for r in records if r["code"] == "3010")
        with self.assertRaisesRegex(ValueError, "deferred"):
            audit_identity_evidence({row["reference_date"]: {}},
                                    [dict(row, effective_date=row["withdrawn_planned_date"])])

    def test_cash_exit_flags_a_quote_during_pre_delisting_halt(self):
        records = json.loads(Path("research/share_identity_evidence.json").read_text())
        row = next(r for r in records if r["code"] == "3454")
        history = {"2026-03-19": {"3454": 99}, "2026-03-27": {"2308": 1000}}
        [result] = audit_identity_evidence(history, [row])["records"]
        self.assertEqual(result["quoted_during_stop"], ["2026-03-19"])
        self.assertIsNone(result["factor"])

    def test_new_shares_issued_to_target_do_not_rebase_acquirer_history(self):
        records = json.loads(Path("research/share_identity_evidence.json").read_text())
        row = next(r for r in records if r["code"] == "1103")
        history = {"2026-07-02": {"1103": 10}, "2026-07-03": {"1103": 11}}
        [result] = audit_identity_evidence(history, [row])["records"]
        self.assertFalse(result["listed_acquirer_quote_boundary_conflict"])
        self.assertIsNone(result["factor"])
        self.assertFalse(result["cross_security_history_splice"])
        history["2026-07-03"].clear()
        [result] = audit_identity_evidence(history, [row])["records"]
        self.assertTrue(result["listed_acquirer_quote_boundary_conflict"])
