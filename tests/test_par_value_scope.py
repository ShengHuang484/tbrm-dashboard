import unittest
from scripts.par_value_scope import review


class VenueTests(unittest.TestCase):
    def test_conflicting_quote_or_missing_date_blocks_otc_exclusion(self):
        event = dict(stock_id="4747", date="2026-08-31")
        notice = dict(code="4747", effective_date=event["date"], notice_url="https://example.org")
        for history, status in [({}, "pending_review"), ({event["date"]: {}}, "tpex_excluded"),
                                ({event["date"]: {"4747": 28}}, "pending_review")]:
            result = review(history, [event], [], [notice])
            self.assertEqual(result["events"][0]["status"], status)

    def test_unmatched_notice_retained_and_duplicate_events_rejected(self):
        notice = dict(code="4747", effective_date="2026-08-31", notice_url="https://example.org")
        event = dict(stock_id="4747", date="2026-08-30")
        result = review({}, [event], [], [notice])
        self.assertEqual(result["evidence_without_candidate"], [("4747", "2026-08-31")])
        self.assertEqual(result["events"][0]["status"], "pending_review")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            review({}, [event, event], [], [])
