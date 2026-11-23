import unittest

from scripts.new_low_replay_check import check_replay


class ArchivedReplayTest(unittest.TestCase):
    def test_same_count_with_wrong_stock_codes_fails(self):
        report = {"factor_count": 1, "score_eligible": False,
                  "sessions": [{"date": "2026-11-20", "removed_low_codes": ["1101"]}]}
        sensitivity = {"score_eligible": False, "sessions": []}
        expected = dict(report, archive_runs=["https://example.com"])
        self.assertTrue(check_replay(report, expected, sensitivity, sensitivity)["archive_replay_verified"])
        changed = dict(report, sessions=[{"date": "2026-11-20", "removed_low_codes": ["1102"]}])
        with self.assertRaisesRegex(ValueError, "removed_low_codes"):
            check_replay(changed, expected, sensitivity, sensitivity)
