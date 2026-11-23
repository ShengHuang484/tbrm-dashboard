import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts.market_refresh import (
    DAILY_FIELDS, DAILY_STOCK_REPORT, MARKET_REPORT, dated_stock_snapshot, check_report, expected_session, refresh, stock_session,
)
from scripts.update_snapshot import archive_daily

NOW = datetime(2026, 11, 23, 8, 11, tzinfo=timezone.utc)
OLD = "2026-11-20"
NEW = "2026-11-23"


def write(folder, name, content):
    (folder / (name + ".json")).write_text(json.dumps(content))


def official_report(*days):
    return dict(stat="OK", fields=["日期", "發行量加權股價指數"],
                data=[[d.replace("-", "/"), "36,811.89"] for d in days])


class RefreshTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        self.calendar = {"years": {"2026": {"closed": ["2026-11-24"]}}}
        write(self.data, "market_calendar", self.calendar)
        write(self.data, "index_history", {"date": OLD})
        write(self.data, "manifest", {"sources": {}, "errors": {}})

    def repo_snapshot(self):
        return {p.name: p.read_bytes() for p in self.data.iterdir()}

    def updater(self, folder, stocks):
        write(folder, "twse_stocks", stocks)
        days = [str(date.fromisoformat(NEW) - timedelta(days=n)) for n in range(251, -1, -1)]
        write(folder, "index_history", {"date": NEW, "rows": [
            {"date": day, "close": 36811.89} for day in days]})
        write(folder, "manifest", {"sources": {
            "twse_stocks": {"status": "ok"},
            "index_history": {"status": "ok", "date": NEW}}, "errors": {}})
        archive_daily(folder, "breadth_history", [{"date": NEW, "up": 100}])

    def test_taiwan_close_weekend_and_holiday(self):
        self.assertEqual(expected_session(NOW, self.calendar), NEW)
        self.assertEqual(expected_session(NOW.replace(hour=5, minute=29), self.calendar), OLD)
        self.assertEqual(expected_session(NOW.replace(day=22), self.calendar), OLD)
        self.assertEqual(expected_session(NOW.replace(day=24), self.calendar), NEW)

    def test_previous_close_after_market_day_preserves_entire_snapshot(self):
        previous = self.repo_snapshot()

        def fetch(url):
            if url.startswith(DAILY_STOCK_REPORT):
                return {"stat": "no data"}
            return official_report(OLD, NEW) if url.startswith(MARKET_REPORT) else [{"Date": "1151120"}]

        status = refresh(self.data, NOW, fetch=fetch, update=self.updater, retry_delays=())
        self.assertEqual(self.repo_snapshot(), previous)
        self.assertEqual((status["status"], status["last_valid_session"]), ("STALE", OLD))
        self.assertEqual(status["source_stock_session"], OLD)
        self.assertFalse(status["date_valid"])

    def test_delayed_api_recovers_and_retries_do_not_duplicate_history(self):
        downloads = iter(([{"Date": "1151120"}], [{"Date": "1151123"}], [{"Date": "1151123"}]))
        waits = []

        def fetch(url):
            if url.startswith(DAILY_STOCK_REPORT):
                return {"stat": "no data"}
            return official_report(NEW) if url.startswith(MARKET_REPORT) else next(downloads)

        first = refresh(self.data, NOW, fetch=fetch, update=self.updater, retry_delays=(30,), pause=waits.append)
        second = refresh(self.data, NOW, fetch=fetch, update=self.updater, retry_delays=())
        self.assertEqual(waits, [30])
        self.assertEqual(first["last_valid_session"], NEW)
        self.assertEqual(second["status"], "PARTIAL")
        self.assertIn("taifex_vix", second["warnings"])
        self.assertTrue(second["date_valid"])
        self.assertEqual(len(json.loads((self.data / "breadth_history.json").read_text())), 1)

    def test_invalid_dates_and_wrong_official_close(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            check_report(official_report(NEW, NEW), NEW)
        with self.assertRaisesRegex(ValueError, "mixed"):
            stock_session([{"Date": "1151120"}, {"Date": "1151123"}])
        previous = self.repo_snapshot()

        def update(folder, stocks):
            self.updater(folder, stocks)
            snapshot = json.loads((folder / "index_history.json").read_text())
            snapshot["rows"][-1]["close"] = 36033.29
            write(folder, "index_history", snapshot)

        status = refresh(self.data, NOW, update=update, retry_delays=(),
                         fetch=lambda url: official_report(NEW) if url.startswith(MARKET_REPORT)
                         else [{"Date": "1151123"}])
        self.assertFalse(status["date_valid"])
        self.assertEqual(self.repo_snapshot(), previous)

    def test_official_dated_report_can_replace_delayed_openapi(self):
        fields = [*DAILY_FIELDS, "漲跌(+/-)", "漲跌價差"]
        rows = [[str(1100+i), "Company", "5,000", "50,000", "10", "10", "10", "10", "30",
                 "<span>-</span>", "0.2"] for i in range(500)]
        dated = {"stat": "OK", "date": "20261123", "tables": [{"fields": fields, "data": rows}]}

        def fetch(url):
            if url.startswith(MARKET_REPORT):
                return official_report(NEW)
            if url.startswith(DAILY_STOCK_REPORT):
                return dated
            return [{"Date": "1151120"}]

        result = refresh(self.data, NOW, fetch=fetch, update=self.updater, retry_delays=())
        self.assertTrue(result["date_valid"])
        self.assertEqual(result["source_stock_session"], OLD)
        self.assertTrue(result["published_stock_source"].startswith(DAILY_STOCK_REPORT))
        self.assertEqual(dated_stock_snapshot(dated, NEW)[0]["Change"], "-0.2")
        with self.assertRaisesRegex(ValueError, "expected session"):
            dated_stock_snapshot(dated, OLD)


class PutCallTests(unittest.TestCase):
    def test_dated_putcall_preserves_trade_volume_basis(self):
        from scripts.update_snapshot import parse_putcall
        header = ["日期", "賣權成交量", "買權成交量", "買賣權成交量比率%",
                  "賣權未平倉量", "買權未平倉量", "買賣權未平倉量比率%"]
        row = ["2026/11/23", "87,845", "162,043", "54.21", "43,378", "140,388", "30.90"]
        html = "<tr>" + "".join(f"<th>{x}</th>" for x in header) + "</tr><tr>" + "".join(
            f"<td>{x}</td>" for x in row) + "</tr>"
        self.assertEqual(parse_putcall(html, NEW)["PutCallVolumeRatio%"], "54.21")
        with self.assertRaisesRegex(ValueError, "report date"):
            parse_putcall(html, OLD)
        with self.assertRaisesRegex(ValueError, "reconcile"):
            parse_putcall(html.replace("54.21", "30.90"), NEW)
