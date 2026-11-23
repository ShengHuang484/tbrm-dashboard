import json
import unittest

from scripts.missing_close_audit import audit, summarize
from scripts.twse_stock_day_gaps import ALTERNATE_URL, capture, collect


class MissingCloseAuditTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = "2026-01-08", "2026-01-09", "2026-01-12"
        self.history = {self.a: {}, self.b: {}, self.c: {"1101": 20, "1102": 30}}
        self.report = dict(market_dates=list(self.history), lookback=2,
                           listing_intervals=[
                               dict(code="1101", listed_from=self.a, delisted_on=None),
                               dict(code="1102", listed_from=self.c, delisted_on=None)],
                           sessions=[dict(date=self.c, eligible_codes=[], adjusted_low_count=0)])
        self.lifecycle = dict(trading_stop_checks=[], coverage=dict(missing_close_pairs=2))
        self.activity = dict(code="1101", conflicting_dates=[], absent_close_reason={})

    def test_groups_market_sessions_and_keeps_short_listing_outside_missing_pairs(self):
        result = audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")
        [group] = result["groups"]
        self.assertEqual(group["pairs"], 2)
        self.assertEqual(group["sole_gap_study_dates"], [self.c])
        self.assertEqual(result["study_day_impact"][0]["insufficient_listing_age"], 1)
        self.assertFalse(result["score_eligible"])

    def test_activity_evidence_does_not_convert_unknown_into_a_halt(self):
        self.activity["absent_close_reason"][self.b] = "activity_without_close"
        result = audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")
        self.assertEqual(result["classification"]["unknown"]["pairs"], 1)
        self.assertEqual(result["study_day_impact"][0]["unknown_only_exclusions"], 0)
        self.activity["absent_close_reason"][self.c] = "zero_reported_activity"
        with self.assertRaisesRegex(ValueError, "overlapping"):
            audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")

    def test_a_price_action_can_rank_a_lead_but_cannot_prove_the_stop(self):
        self.report["applied_events"] = [
            dict(code="1101", ex_date=self.c, event_type="capital_reduction",
                 source_url="https://example.com/resumption")]
        result = audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")
        [lead] = result["possible_action_stops"]
        self.assertEqual(lead["observed_resumption"], self.c)
        self.assertEqual(result["classification"]["unknown"]["pairs"], 2)

    def test_priority_partition_and_summary_are_reproducible(self):
        dates = [self.a, self.b, self.c, "2026-01-13", "2026-01-14"]
        critical = "1101"
        high = "1102"
        historical = [str(code) for code in range(1200, 1222)]
        history = {day: {} for day in dates}
        for day in (dates[0], dates[2], dates[4]):
            history[day][high] = 10
        for day in dates[1:]:
            history[day][critical] = 10
        report = dict(market_dates=dates, lookback=4, listing_intervals=[
            dict(code=code, listed_from=dates[0], delisted_on=dates[1] if code in historical else None)
            for code in (critical, high, *historical)],
            sessions=[dict(date=dates[-1], eligible_codes=[], adjusted_low_count=0)])
        self.lifecycle["coverage"]["missing_close_pairs"] = 25
        result = audit(history, report, self.lifecycle, self.activity, "https://example.com")
        queue = result["unknown_priority_queue"]
        self.assertEqual([r["priority"] for r in queue], ["critical", "high", "high"] + ["historical"] * 22)
        self.assertEqual(sum(r["pairs"] for r in queue), 25)
        self.assertEqual(sum(r["pairs"] for r in result["classification"].values()), 25)
        preview = summarize(result)
        self.assertEqual(preview["unknown_priority_queue"], queue[:20])
        self.assertTrue(preview["priority_queue_truncated"])
        self.assertEqual(result["unknown_group_count"], len(result["groups"]))
        self.assertEqual(len(result["unknown_priority_queue"]), 25)

    def test_rejects_inconsistent_report_or_denominator(self):
        self.report["sessions"][0]["eligible_codes"] = ["1101"]
        with self.assertRaisesRegex(ValueError, "strict quote windows"):
            audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")
        self.report["sessions"][0]["eligible_codes"] = []
        self.lifecycle["coverage"]["missing_close_pairs"] = 1
        with self.assertRaisesRegex(ValueError, "denominator"):
            audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com")

    def test_official_rows_distinguish_zero_activity_and_archival_price_gap(self):
        raw = dict(stat="OK", date="20260101", title="115年01月 1101 Test",
                   fields=["日期", "成交股數", "成交筆數", "收盤價"],
                   data=[["115/01/08", "100", "5", "22"], ["115/01/09", "0", "0", "--"]])
        evidence = capture("1101", "2026-01", [self.a, self.b], json.dumps(raw).encode())
        result = audit(self.history, self.report, self.lifecycle, self.activity,
                       "https://example.com", [evidence])
        self.assertEqual(result["classification"]["official_close_missing_from_archive"]["pairs"], 1)
        self.assertEqual(result["classification"]["zero_reported_activity"]["pairs"], 1)
        self.assertFalse(result["study_day_impact"][0]["potential_quote_recovery_codes"])
        self.assertEqual(self.history[self.a], {})
        evidence["raw_rows"][1][-1] = "22"
        with self.assertRaisesRegex(ValueError, "digest"):
            audit(self.history, self.report, self.lifecycle, self.activity, "https://example.com", [evidence])

    def test_official_row_absence_never_implies_suspension(self):
        raw = dict(stat="OK", date="20260101", title="115年01月 1101 Test",
                   fields=["日期", "成交股數", "成交筆數", "收盤價"],
                   data=[["115/01/12", "100", "5", "20"]])
        evidence = capture("1101", "2026-01", [self.a], json.dumps(raw).encode())
        result = audit(self.history, self.report, self.lifecycle, self.activity,
                       "https://example.com", [evidence])
        self.assertEqual(result["official_quote_diagnostics"], {"official_row_absent": 1})
        self.assertEqual(result["unknown_pairs"], 2)
        raw["data"].append(raw["data"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            capture("1101", "2026-01", [self.a], json.dumps(raw).encode())

    def test_collection_ranks_new_monthly_requests_by_remaining_pairs(self):
        raw = dict(stat="OK", date="20260101", title="115年01月 1101 Test",
                   fields=["日期", "成交股數", "成交筆數", "收盤價"],
                   data=[["115/01/08", "0", "0", "--"]])
        evidence = capture("1101", "2026-01", [self.a], json.dumps(raw).encode())
        calls = []

        def download(url):
            calls.append(url)
            return json.dumps(dict(raw, title="115年01月 1102 Test")).encode()

        queue = [dict(code=code, first=self.a, last=self.b, priority="high") for code in ("1101", "1102")]
        result = collect(queue, [self.a, self.b, self.c], download, ["high"], 1, lambda: None,
                         existing=[evidence], rank_by_pairs=True, endpoint=ALTERNATE_URL)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].endswith("stockNo=1102"))
        self.assertEqual(result["batches"][0]["source_url"], calls[0])
        self.assertTrue(calls[0].startswith(ALTERNATE_URL))
        self.assertEqual(result["batches"][0]["requested_sessions"], [self.a, self.b])
        self.assertEqual(result["planned_requests"], 2)
