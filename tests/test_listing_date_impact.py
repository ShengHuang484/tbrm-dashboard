import unittest

from scripts.listing_date_impact import audit


class ListingDateImpactTest(unittest.TestCase):
    def test_detects_candidate_crossing_lookback_without_editing_archive(self):
        checkpoint = dict(
            history={"2026-01-05": {"1303": "10"}, "2026-01-06": {"1303": "9"}},
            listing_intervals=[dict(code="1303", listed_from="2026-01-05", delisted_on=None)],
            applied_events=[],
            lookback=1,
        )
        review = dict(listing_start_differences=[
            dict(code="1303", archived="2026-01-05", isin="2026-01-06", status="REVIEW"),
        ])
        result = audit(checkpoint, review)
        self.assertEqual(result["changed_market_sessions"], ["2026-01-06"])
        self.assertEqual(result["cases"]["1303"]["eligibility_changed_sessions"], ["2026-01-06"])
        self.assertEqual(result["cases"]["1303"]["adjusted_low_membership_changed_sessions"],
                         ["2026-01-06"])
        self.assertEqual(checkpoint["listing_intervals"][0]["listed_from"], "2026-01-05")
        self.assertFalse(result["score_eligible"])
