import unittest

from scripts.quote_absence_evidence import check_halt, reconcile_quotes


class AbsenceTests(unittest.TestCase):
    def test_zero_close_with_turnover_does_not_establish_halt(self):
        history = {"2026-11-19": {}, "2026-11-20": {}}
        rows = [dict(date=d, stock_id="1538", close=0, Trading_Volume=v, Trading_turnover=v)
                for d,v in zip(history, (1, 0))]
        result = reconcile_quotes(history, "1538", dict(status=200, data=rows))
        self.assertEqual(list(result["absent_close_reason"].values()),
                         ["activity_without_close", "zero_reported_activity"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            reconcile_quotes(history, "1538", dict(status=200, data=rows[:-1]))

    def test_official_halt_excludes_resumption_and_flags_conflicting_quotes(self):
        history = {d: {"1808": 31} for d in ("2026-11-11", "2026-11-20", "2026-11-23")}
        result = check_halt(history, dict(code="1808", stop_from="2026-11-12",
                            resumption_date="2026-11-23", last_pre_stop_date="2026-11-11",
                            pre_stop_close="31"))
        self.assertEqual(result["conflicting_dates"], ["2026-11-20"])
