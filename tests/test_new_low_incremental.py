import json
import unittest

from scripts.new_low_incremental import advance, digest


class IncrementalTest(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = "2025-12-30", "2025-12-31", "2026-01-02"
        self.listings = [dict(code="1101", listed_from=self.a, delisted_on=None)]
        state = dict(history={self.a: {"1101": 13}, self.b: {"1101": 12}},
                     listing_intervals=self.listings, applied_events=[], lookback=1, retention_sessions=2)
        self.checkpoint = self.encode(state)
        self.plan = dict(origin="synthetic", mode="append", as_of=self.c,
                         session=self.c, checkpoint_sha256=digest(self.checkpoint))
        self.inputs = dict(calendar=[
            dict(date="2026-01-01", state="closed", reason="holiday"),
            dict(date=self.c, state="open", reason="reported market session")],
            quotes=dict(stat="OK", date="20260102", tables=[
                dict(fields=["證券代號", "收盤價"], data=[["1101", "11"]])]),
            listings=dict(date=self.c, intervals=self.listings, excluded_codes=[]),
            actions=dict(date=self.c, coverage_reviewed=True, events=[]),
            gaps=dict(date=self.c, reasons={}))

    @staticmethod
    def encode(value):
        return json.dumps(value).encode()

    def run_update(self, *, allow_correction=False):
        files = {k: self.encode(v) for k, v in self.inputs.items()}
        self.plan["sources"] = {k: dict(source_url=f"https://example.com/{k}", sha256=digest(v))
                                for k, v in files.items()}
        return advance(self.checkpoint, self.plan, files.__getitem__, allow_correction=allow_correction)

    def test_cross_year_and_holiday_roll_the_market_window(self):
        self.inputs["quotes"]["tables"].append({"title": "unrelated market table"})
        result = self.run_update()
        self.assertEqual(list(result["checkpoint"]["history"]), [self.b, self.c])
        self.assertEqual(result["report"]["sessions"][0]["adjusted_low_codes"], ["1101"])
        self.assertFalse(result["score_eligible"])

    def test_calendar_gap_is_blocked_and_typhoon_is_closed(self):
        self.inputs["calendar"].pop(0)
        with self.assertRaisesRegex(ValueError, "every elapsed date"):
            self.run_update()
        self.inputs["calendar"].insert(0, dict(date="2026-01-01", state="closed", reason="holiday"))
        self.inputs["calendar"][-1].update(state="closed", reason="typhoon notice")
        result = self.run_update()
        self.assertEqual(result["status"], "closed")
        self.assertNotIn("report", result)

    def test_delayed_quote_and_unattested_actions_are_blocked(self):
        self.inputs["quotes"]["date"] = "20251231"
        with self.assertRaisesRegex(ValueError, "delayed"):
            self.run_update()
        self.inputs["quotes"]["date"] = "20260102"
        self.inputs["actions"]["coverage_reviewed"] = False
        with self.assertRaisesRegex(ValueError, "action evidence"):
            self.run_update()

    def test_correction_requires_explicit_consent_and_replays(self):
        self.plan.update(mode="correction", session=self.b, revision_note="Reissued closing quote")
        self.inputs["calendar"] = [dict(date=self.b, state="open", reason="historical open")]
        for name in ("gaps", "listings", "actions"):
            self.inputs[name]["date"] = self.b
        self.inputs["quotes"]["date"] = "20251231"
        with self.assertRaisesRegex(ValueError, "explicit approval"):
            self.run_update()
        result = self.run_update(allow_correction=True)
        self.assertEqual(result["checkpoint"]["history"][self.b]["1101"], "11")
        self.assertEqual(result["checkpoint"]["session_evidence"][self.b]["revision_note"],
                         "Reissued closing quote")
        self.assertFalse(result["score_eligible"])

    def test_missing_status_and_unclassified_codes_fail_closed(self):
        self.inputs["quotes"]["tables"][0]["data"].append(["1102", "12"])
        with self.assertRaisesRegex(ValueError, "scope decision"):
            self.run_update()
        self.inputs["listings"]["intervals"] += [dict(code="1103", listed_from=self.c, delisted_on=None)]
        self.inputs["listings"]["excluded_codes"] = ["1102"]
        with self.assertRaisesRegex(ValueError, "missing-price evidence"):
            self.run_update()
        self.inputs["gaps"]["reasons"] = {"1103": "announced_stop"}
        self.assertEqual(self.run_update()["checkpoint"]["gap_reasons"][self.c], {"1103": "announced_stop"})
