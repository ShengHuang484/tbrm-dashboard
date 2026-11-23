import unittest

from scripts.session_action_coverage import action_date_control


class ActionSourceDateTest(unittest.TestCase):
    def test_preannouncement_uses_resumption_date_even_when_bounds_are_echoed(self):
        payload = dict(stat="OK", params=dict(startDate="20261120", endDate="20261124"),
                       fields=["停止買賣日期", "恢復買賣日期"],
                       data=[["115/08/27", "115/09/07"], ["115/11/23", ""]])
        result = action_date_control(payload, "恢復買賣日期", "2026-11-20", "2026-11-24")
        self.assertEqual(result["outside_window"], ["2026-09-07"])
        self.assertEqual(result["rows_without_effective_date"], 1)

    def test_initial_listing_date_cannot_be_replaced_with_application_date(self):
        payload = dict(stat="OK", fields=["申請日期"], data=[["115.11.23"]])
        with self.assertRaisesRegex(ValueError, "missing or ambiguous date field"):
            action_date_control(payload, "股票上市買賣日期", "2026-11-20", "2026-11-24")
