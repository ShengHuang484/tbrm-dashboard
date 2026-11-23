import unittest

from scripts.new_low_replay_check import check_replay, membership_digest


class ArchivedReplayTest(unittest.TestCase):
    def test_same_count_with_wrong_stock_codes_fails(self):
        report = {"factor_count": 1, "score_eligible": False,
                  "sessions": [{"date": "2026-11-20", "removed_low_codes": ["1101"],
                                "strict_eligible": 2, "eligible_codes": ["1101", "1102"],
                                "adjusted_low_count": 1, "adjusted_low_codes": ["1102"]}]}
        sensitivity = {"score_eligible": False, "sessions": []}
        row = report["sessions"][0]
        expected = dict(report, sessions=[dict(row, membership_sha256=membership_digest(row))])
        self.assertTrue(check_replay(report, expected, sensitivity, sensitivity)["archive_replay_verified"])
        changed = dict(report, sessions=[dict(row, removed_low_codes=["1102"])])
        with self.assertRaisesRegex(ValueError, "removed_low_codes"):
            check_replay(changed, expected, sensitivity, sensitivity)

        for changes in ({"eligible_codes": ["1103", "1102"]}, {"adjusted_low_codes": ["1101"]}):
            with self.assertRaisesRegex(ValueError, "membership mismatch"):
                check_replay(dict(report, sessions=[dict(row, **changes)]), expected,
                             sensitivity, sensitivity)

    def test_duplicate_security_is_not_a_second_observation(self):
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            membership_digest(dict(eligible_codes=["1101", "1101"], strict_eligible=2,
                                   adjusted_low_codes=[], adjusted_low_count=0))
