import json
import unittest
from fractions import Fraction
from pathlib import Path

from scripts.action_completeness import audit, assemble, classify_latest_lookback_gaps
from scripts.corporate_action_audit import event_factors


def read(path):
    return json.loads(Path(path).read_text())


class ActionCompletenessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = read("data/history/new_low_closes.json")
        cls.evidence = [
            read("research/ex_right_date_results.json"),
            read("research/finmind_action_crosscheck.json"),
            read("research/face_value_issuers.json"),
            read("research/lifecycle_crosscheck_results.json")["reduction_pre_window_close"],
        ]

    def test_archive_factors_and_unexplained_price_jumps(self):
        report = audit(self.history, *self.evidence)
        factors = event_factors(report["applied_events"], number=Fraction)
        self.assertEqual(len(factors), 33)
        self.assertEqual(factors["8422", "2025-11-17"], Fraction(1, 10))
        self.assertEqual(factors["7780", "2026-01-19"], Fraction(1, 10))
        self.assertEqual(factors["6949", "2026-09-07"], Fraction(1, 20))
        self.assertEqual([row["code"] for row in report["boundary_events"]], ["2832"])
        self.assertEqual({row["code"] for row in report["unexplained_discontinuities"]},
                         {"6921", "6669"})
        self.assertFalse(report["score_eligible"])

    def test_face_value_must_match_published_reference(self):
        ex_right, crosscheck, face_actions, boundary = self.evidence
        changed = [dict(face_actions[0], new_face_value="2"), *face_actions[1:]]
        with self.assertRaisesRegex(ValueError, "face-value reference mismatch"):
            assemble(self.history, ex_right, crosscheck, changed, boundary)

    def test_action_bounded_does_not_include_other_gaps_in_same_stock(self):
        data = {
            "2026-01-05": {"1101": 10}, "2026-01-06": {},
            "2026-01-07": {"1101": 5}, "2026-01-08": {},
            "2026-01-09": {"1101": 6},
        }
        event = {"code": "1101", "ex_date": "2026-01-07", "event_type": "split"}
        result = classify_latest_lookback_gaps(data, [event], 4)
        self.assertEqual(result["action_bounded_missing_pairs"], 1)
        self.assertEqual(result["other_missing_pairs"], 1)
        self.assertEqual(result["codes_missing_prior_quotes"], 1)
        self.assertFalse(result["verified_halt_dates"])
