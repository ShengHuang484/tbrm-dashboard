import unittest
from datetime import date, timedelta

from scripts.new_low_research_backtest import EMBARGO, TRAIN, evaluate, predictions


class ResearchBacktestTest(unittest.TestCase):
    def test_future_values_and_embargo_cannot_change_an_earlier_signal(self):
        first = date(2020, 1, 1)
        rows = [
            dict(index=i, date=(first + timedelta(days=i)).isoformat(), baseline=i, count=i,
                 share=i, contraction=i)
            for i in range(TRAIN + EMBARGO + 3)
        ]
        prediction = predictions(rows, len(rows) + 60)[0]
        self.assertEqual(prediction["index"], TRAIN + EMBARGO)
        self.assertEqual(prediction["train_end"], rows[TRAIN - 1]["date"])
        for row in rows[TRAIN:]:
            row["baseline"] = row["count"] = row["share"] = row["contraction"] = -10
        # Restore the scoring day's close-time features; change only excluded rows.
        day = TRAIN + EMBARGO
        rows[day].update(baseline=day, count=day, share=day, contraction=day)
        self.assertEqual(predictions(rows, len(rows) + 60)[0]["signals"], prediction["signals"])

    def test_gate_does_not_publish_metrics_without_enough_samples(self):
        report = dict(score_eligible=False, lookback=252, quote_policy="strict_market_sessions",
                      market_dates=["2026-11-20"],
                      sessions=[dict(date="2026-11-20", eligible_count=100, adjusted_low_count=12)])
        result = evaluate(report, {"2026-11-20": 100}, {})
        self.assertEqual(result["status"], "INSUFFICIENT_SAMPLE")
        self.assertEqual(result["counts"]["future_close_windows"]["5"], 0)
        self.assertIsNone(result["metrics"])
        with self.assertRaisesRegex(ValueError, "as-of-close"):
            evaluate(report, {"2026-11-20": 100}, {
                "2026-11-20": dict(available_on="2026-11-23", confirmation_score=50),
            })
