import json
import unittest
from pathlib import Path

from scripts.new_low_adjusted_audit import audit_adjusted_lows


class AdjustedNewLowTest(unittest.TestCase):
    def test_independent_raw_baseline_matches_archived_counts_and_denominators(self):
        history = json.loads(Path("data/history/new_low_closes.json").read_text())
        snapshot = json.loads(Path("data/new_low.json").read_text())
        archive = snapshot["dynamic_universe_research_only"]
        report = audit_adjusted_lows(history, [])
        rows = report["sessions"]
        self.assertEqual([x["date"] for x in rows], snapshot["window_dates"])
        self.assertEqual([x["raw_low_count"] for x in rows], archive["counts"])
        self.assertEqual([x["adjusted_low_count"] for x in rows], archive["counts"])
        self.assertEqual([x["strict_eligible"] for x in rows], archive["eligible_stock_counts"])
        self.assertEqual([x["missing_prior_quote"] for x in rows], archive["missing_lookback_counts"])
        self.assertFalse(report["score_eligible"])

    def test_compound_factors_ties_future_events_and_missing_quotes(self):
        days = [f"2026-07-{i:02d}" for i in (6, 7, 8, 9, 13)]
        # Independently calculated final adjusted lookback for 2008:
        # 120 * (1/3) * (3/4) = 30; 44 * (3/4) = 33; 31 remains 31.
        history = {
            days[0]: {"2008": 120, "2610": 50, "3055": 40},
            days[1]: {"2008": 44, "3055": 39},
            days[2]: {"2008": 31, "2610": 49, "3055": 38},
            days[3]: {"2008": 30, "2610": 48, "3055": 37},
            days[4]: {"2008": 29, "2610": 47, "3055": 36},
        }
        events = [
            self.event("2008", days[1], 120, 40),
            self.event("2008", days[2], 44, 33),
            self.event("3055", days[4], 37, 18.5),
        ]
        rows = audit_adjusted_lows(history, events, lookback=3)["sessions"]
        self.assertEqual(rows[0]["strict_eligible"], 2)
        self.assertEqual(rows[0]["missing_prior_quote"], 1)
        self.assertEqual(rows[0]["raw_low_count"], 2)
        self.assertEqual(rows[0]["adjusted_low_count"], 1)
        self.assertEqual(rows[0]["removed_low_codes"], ["2008"])
        self.assertEqual(rows[1]["removed_low_codes"], ["3055"])

    def test_rejects_unverified_event_and_event_without_observed_close(self):
        history = {"2026-07-09": {"2008": 20}, "2026-07-13": {"2008": 19}}
        event = self.event("2008", "2026-07-13", 20, 19)
        with self.assertRaisesRegex(ValueError, "unverified"):
            audit_adjusted_lows(history, [dict(event, verified=False)], lookback=1)
        with self.assertRaisesRegex(ValueError, "current-session"):
            audit_adjusted_lows(history, [dict(event, ex_date="2026-07-10")], lookback=1)
        with self.assertRaisesRegex(ValueError, "differs from raw history"):
            audit_adjusted_lows(history, [dict(event, prior_close=21)], lookback=1)

    @staticmethod
    def event(code, day, prior, reference):
        return {
            "code": code, "ex_date": day, "prior_close": prior,
            "reference_price": reference, "verified": True,
            "source_url": "https://example.com/test", "event_type": "fixture",
        }
