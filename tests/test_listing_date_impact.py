import unittest
from unittest.mock import patch

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

    def test_proves_equal_archive_intervals_without_recalculating_lows(self):
        checkpoint = dict(
            history={"2025-10-22": {"1303": "10"}, "2025-10-23": {"1303": "9"}},
            listing_intervals=[dict(code="1303", listed_from="1967-11-15", delisted_on=None)],
            applied_events=[],
            lookback=1,
        )
        review = dict(listing_start_differences=[
            dict(code="1303", archived="1967-11-15", isin="1967-11-05", status="REVIEW"),
        ])
        with patch("scripts.listing_date_impact.audit_adjusted_lows") as replay:
            result = audit(checkpoint, review)
        replay.assert_not_called()
        self.assertEqual(result["method"], "archive_boundary_proof")
        self.assertEqual(result["archive_sessions"], 2)
        self.assertEqual(result["changed_market_sessions"], [])
        self.assertTrue(result["cases"]["1303"]["clamped_intervals_equal"])
