import json
import unittest
from pathlib import Path

from scripts.corporate_action_external_validation import audit_delistings, compare_transition


class ExternalValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = json.loads(Path("data/history/new_low_closes.json").read_text())
        cls.evidence = json.loads(Path("research/external_transition_evidence.json").read_text())

    def test_independent_prices_allow_rescaling_but_reject_wrong_factor(self):
        for row in self.evidence["transitions"]:
            self.assertTrue(compare_transition(self.history, row)["agrees_with_display_precision"])
            self.assertFalse(compare_transition(
                self.history, dict(row, reference="100"))["agrees_with_display_precision"])

    def test_delisted_identity_is_never_carried_to_successor(self):
        reports = audit_delistings(self.history, self.evidence["delistings"])
        self.assertEqual(len(reports), 5)
        self.assertTrue(all(r["last_pre_delisting_close_date"] for r in reports))
        self.assertTrue(all(not r["post_boundary_quote_dates"] for r in reports))
        self.assertFalse(any(r["carry_history_to_successor"] for r in reports))
        [bad] = audit_delistings({"2026-09-01": {"2867": 3}}, [self.evidence["delistings"][3]])
        self.assertEqual(bad["post_boundary_quote_dates"], ["2026-09-01"])
