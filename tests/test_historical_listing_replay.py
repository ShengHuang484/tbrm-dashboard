import unittest

from scripts.historical_listing_replay import replay


class HistoricalListingReplayTest(unittest.TestCase):
    def test_reused_code_cannot_borrow_pre_exit_prices(self):
        a, b, c = "2026-01-02", "2026-01-05", "2026-01-06"
        history = {a: {"1101": 5, "1102": 30}, b: {"1101": 4, "1102": 29},
                   c: {"1101": 3, "1102": 28}}
        roster = [dict(code="1101", listed_from=b, industry="01"),
                  dict(code="1102", listed_from=a, industry="01")]
        prior = dict(code="1101", listed_from=a, delisted_on=b,
                     listing_source="https://example.com/list", exit_source="https://example.com/exit")
        evidence = dict(snapshot_date=c, historical_exits=[prior])
        result = replay(history, dict(applied_events=[], lookback=1), roster, evidence)
        self.assertEqual([row["eligible"] for row in result["sessions"]], [1, 2])
        self.assertFalse(result["listing_universe_verified"])
        strict = replay(history, dict(applied_events=[], lookback=1), roster, evidence,
                        strict_report=True)
        self.assertEqual(strict["sessions"][0]["eligible_codes"], ["1102"])
        self.assertFalse(strict["score_eligible"])
        evidence["historical_exits"].clear()
        result = replay(history, dict(applied_events=[], lookback=1), roster, evidence)
        self.assertEqual(result["outside_listing_quotes"], {a: ["1101"]})
        with self.assertRaisesRegex(ValueError, "outside reconstructed"):
            replay(history, dict(applied_events=[], lookback=1), roster, evidence, strict_report=True)

    def test_announced_halt_rejects_a_close_during_stop_or_missing_restart(self):
        a, b, c = "2026-01-02", "2026-01-05", "2026-01-06"
        history = {a: {"6806": 5}, b: {"6806": 5}, c: {}}
        roster = [dict(code="6806", listed_from=a, industry="01")]
        stop = dict(code="6806", start=b, end=c, disposition="resume",
                    sources=["https://example.com/halt"])
        evidence = dict(snapshot_date=c, historical_exits=[], trading_stops=[stop])
        result = replay(history, dict(applied_events=[], lookback=1), roster, evidence)
        [check] = result["trading_stop_checks"]
        self.assertEqual(check["conflicting_sessions"], [b, c])
