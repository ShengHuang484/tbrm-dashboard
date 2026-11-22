import unittest
from decimal import Decimal
from scripts.corporate_action_audit import backward_adjusted_series, event_factors


def event(**kw):
    e = dict(code="2330", ex_date="2026-06-02", prior_close="100",
             reference_price="95", verified=True, event_type="cash_dividend",
             source_url="https://www.twse.com.tw/example")
    e.update(kw)
    return e


class CorporateActionTests(unittest.TestCase):
    def test_adjusts_prior_close_only(self):
        result = backward_adjusted_series(
            ["2026-06-01", "2026-06-02", "2026-06-03"],
            {"2330": [100, 95, 96]}, [event()])
        self.assertEqual(result["2330"], [Decimal("95.00"), Decimal("95"), Decimal("96")])

    def test_multiple_events_compound(self):
        result = backward_adjusted_series(
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"],
            {"2330": [100, 95, 95, 90]},
            [event(), event(ex_date="2026-06-04", prior_close="95", reference_price="90")])
        self.assertEqual(result["2330"][0], Decimal("90.0000"))

    def test_rejects_unverified(self):
        with self.assertRaises(ValueError):
            event_factors([event(verified=False)])

    def test_rejects_missing_source(self):
        with self.assertRaises(ValueError):
            event_factors([event(source_url="")])

    def test_rejects_duplicate(self):
        with self.assertRaises(ValueError):
            event_factors([event(), event()])

    def test_rejects_event_without_stock_series(self):
        with self.assertRaisesRegex(ValueError, "no matching stock price series"):
            backward_adjusted_series(["2026-06-01", "2026-06-02"],
                                     {"2317": [100, 99]}, [event()])

    def test_rejects_missing_close(self):
        with self.assertRaises(ValueError):
            backward_adjusted_series(["2026-06-01"], {"2330": [None]}, [])


if __name__ == "__main__":
    unittest.main()
