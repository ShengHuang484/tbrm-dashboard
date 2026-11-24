import json
import unittest
from pathlib import Path

from scripts.new_low_date_scenario import audit_date_scenario


class DateScenarioTests(unittest.TestCase):
    def test_real_auction_evidence_changes_only_one_low_classification(self):
        history = json.loads(Path("data/history/new_low_closes.json").read_text())
        evidence = json.loads(Path("research/ex_right_date_results.json").read_text())
        report = audit_date_scenario(history, evidence)
        changed = [row for row in report["sessions"] if row["added_low_codes"] or row["removed_low_codes"]]
        self.assertEqual([(row["date"], row["removed_low_codes"]) for row in changed],
                         [("2026-11-10", ["6931"])])
        self.assertEqual(report["factor_count"], 10)
        self.assertFalse(report["score_eligible"])
        evidence["cases"][0]["official_trading_basis_matches"] = False
        with self.assertRaisesRegex(ValueError, "needs reconciled"):
            audit_date_scenario(history, evidence)
