import unittest

from scripts.new_low_research_preview import markdown


class ResearchPreviewTest(unittest.TestCase):
    def test_blocked_or_unavailable_sessions_are_rendered_without_counts(self):
        result = dict(sessions={"2026-11-23": dict(status="BLOCKED"),
                                "2026-11-24": dict(status="unavailable")},
                      historical_coverage=dict(denominator_sessions=262,
                                               internally_reconstructed_sessions=262,
                                               external_independently_verified_sessions=0),
                      activation_blockers=[])
        output = markdown(result)
        self.assertIn("| 2026-11-23 | BLOCKED | — | — | — |", output)
        self.assertIn("| 2026-11-24 | unavailable | — | — | — |", output)
