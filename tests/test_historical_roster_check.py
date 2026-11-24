import hashlib
import unittest

from scripts.historical_roster_check import check


class RosterCheckTest(unittest.TestCase):
    def setUp(self):
        self.dates = ["2025-12-31", "2026-01-02", "2026-01-05"]
        self.report = dict(market_dates=self.dates, listing_intervals=[
            dict(code="1101", listed_from=self.dates[0], delisted_on=self.dates[1]),
            dict(code="1102", listed_from=self.dates[1], delisted_on=None)])
        self.roster = (b"date,code,security_id\n2025-12-31,1101,S1\n"
                       b"2026-01-02,1102,S1\n2026-01-02,1101,S2\n")

    def manifest(self, content):
        return dict(origin="synthetic", source_url="https://example.com/fixture",
                    retrieved_on="2026-01-05", covered_dates=self.dates[:2],
                    sha256=hashlib.sha256(content).hexdigest())

    def test_dated_membership_transition_and_uncovered_day(self):
        result = check(self.report, self.manifest(self.roster), self.roster)
        before, current, missing = result["sessions"]
        self.assertEqual(before["reconstructed_only"], [])
        self.assertEqual(current["observed_only"], ["1101"])
        self.assertEqual(current["adjacent_changes"]["reused_codes"], ["1101"])
        self.assertEqual(current["adjacent_changes"]["ticker_transitions"][0]["security_id"], "S1")
        self.assertIsNone(missing["observed_members"])
        self.assertEqual(result["unconfirmed_ranges"], [dict(first=self.dates[-1], last=self.dates[-1], sessions=1)])
        self.assertFalse(result["independent_universe_verified"])

    def test_hash_and_daily_duplicates_are_rejected(self):
        duplicate = self.roster + b"2026-01-02,1103,S1\n"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            check(self.report, self.manifest(duplicate), duplicate)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            check(self.report, self.manifest(self.roster), duplicate)

    def test_reconstruction_alone_has_no_external_coverage(self):
        result = check(self.report)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["observed_sessions"], 0)
        self.assertEqual(result["unconfirmed_ranges"][0]["sessions"], 3)
        self.assertEqual(result["coverage"]["internally_reconstructed_sessions"], 3)
        self.assertEqual(result["coverage"]["external_independently_verified_sessions"], 0)

    def test_same_source_and_external_delivery_have_separate_coverage(self):
        manifest = dict(self.manifest(self.roster), origin="twse", source_url="https://isin.twse.com.tw/")
        stats = check(self.report, manifest, self.roster)["coverage"]
        self.assertEqual(stats["official_same_source_checked_sessions"], 2)
        self.assertEqual(stats["official_unverified_ranges"][0]["sessions"], 1)
        self.assertEqual(stats["independent_unverified_ranges"][0]["sessions"], 3)
        manifest.update(origin="external", upstream_source="TWSE", usage_basis="fixture")
        stats = check(self.report, manifest, self.roster)["coverage"]
        self.assertEqual(stats["external_candidate_sessions"], 2)
        self.assertEqual(stats["external_independently_verified_sessions"], 0)

    def test_lifecycle_counts_do_not_change_daily_observations(self):
        evidence = dict(market_sessions=3, outside_listing_quotes={}, coverage={
            "archive_new_listing_matches": 2,
            "archived_delisting_check": dict(date_window=[self.dates[0], self.dates[-1]], matched=1,
                                            source_sha256="a" * 64)})
        stats = check(self.report, lifecycle=evidence)["coverage"]
        self.assertEqual(stats["verified_same_source_lifecycle_events"]["delistings"], 1)
        self.assertEqual(stats["official_same_source_checked_sessions"], 0)
        evidence["market_sessions"] = 2
        with self.assertRaisesRegex(ValueError, "window"):
            check(self.report, lifecycle=evidence)

    def test_contiguous_observations_show_returned_code_and_identifier_disagreement(self):
        content = (b"date,code,security_id\n2025-12-31,1101,S1\n"
                   b"2026-01-02,1102,S2\n2026-01-05,1102,S2\n2026-01-05,1101,S3\n")
        self.report["listing_intervals"][0]["security_id"] = "LOCAL-S1"
        manifest = dict(self.manifest(content), covered_dates=self.dates)
        result = check(self.report, manifest, content)
        self.assertEqual(result["delivery_coverage_status"], "PASS")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["sessions"][0]["identity_mismatches"][0]["observed"], "S1")
        self.assertEqual(result["sessions"][-1]["adjacent_changes"]["returned_codes"],
                         [dict(code="1101", prior_security_id="S1", security_id="S3")])
