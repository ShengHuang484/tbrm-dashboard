import io
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from scripts.market_refresh import (
    DAILY_FIELDS, DAILY_STOCK_REPORT, MARKET_REPORT, dated_stock_snapshot, check_report, expected_session, refresh,
    source_warnings, stock_session,
)
from scripts.update_snapshot import (
    MarginRedirectHandler, MarginReportError, archive_daily, dated_margin_report,
    fetch_dated_margin, maintenance, margin_total,
)

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

    def test_verified_same_session_survives_transport_error(self):
        self.updater(self.data, [{"Date": "1151123"}])
        write(self.data, "market_update_status", {"date_valid": True, "last_valid_session": NEW})

        def unavailable(url):
            raise OSError("temporary upstream failure")

        result = refresh(self.data, NOW, fetch=unavailable, retry_delays=())
        self.assertTrue(result["date_valid"])
        self.assertEqual(result["download_status"], "retained_verified")
        self.assertEqual(result["last_valid_session"], NEW)


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


class DatedMarginTests(unittest.TestCase):
    @staticmethod
    def report(day, value="100,000"):
        return {"stat": "OK", "date": day.replace("-", ""), "tables": [
            {"fields": ["項目", "今日餘額"], "data": [["融資金額(仟元)", value]]}
        ]}

    def test_backfill_uses_verified_sessions_only_and_reuses_history(self):
        weekdays = [date(2026, 10, 22) + timedelta(days=n) for n in range(33)]
        sessions = [str(d) for d in weekdays if d.weekday() < 5 and str(d) != "2026-10-26"][-21:]
        calls = []

        def loader(day):
            calls.append(day)
            if day == NEW and calls.count(NEW) == 1:
                return dated_margin_report(day, lambda url: ({"stat": "很抱歉，沒有符合條件的資料"}, url))
            return self.report(day), "https://example.org"

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            archive_daily(folder, "twse_dated_margin", [{"date": "2026-10-21", "balance_1000_twd": 1}])
            partial, raw = fetch_dated_margin(folder, sessions, loader)
            self.assertEqual(partial["missing"], [NEW])
            self.assertIsNone(raw)
            diagnostic = json.loads((folder / "twse_dated_margin_diagnostic.json").read_text())
            self.assertEqual(diagnostic["valid_days"], 20)
            self.assertEqual([route["status"] for route in diagnostic["attempts"][0]["routes"]],
                             ["no_report", "no_report"])
            self.assertIn("no_report", source_warnings(folder, {"sources": {"twse_dated_margin": partial}},
                                                       NEW)["twse_dated_margin"])
            valid, raw = fetch_dated_margin(folder, sessions, loader)
            self.assertEqual(valid["missing"], [])
            self.assertEqual(calls[-1], NEW)
            self.assertEqual(len(calls), 22)
            self.assertEqual(len(json.loads((folder / "twse_dated_margin.json").read_text())), 22)

    def test_report_requires_named_amount_column_and_finite_value(self):
        self.assertEqual(margin_total(self.report(NEW)), 100000)
        for value in ("NaN", "Infinity", "0"):
            with self.assertRaises(ValueError):
                margin_total(self.report(NEW, value))
        raw = self.report(NEW)
        raw["tables"][0]["fields"][1] = "前日餘額"
        with self.assertRaises(ValueError):
            margin_total(raw)

    def test_route_falls_back_after_malformed_report_to_legacy_table(self):
        legacy = {"stat": "OK", "date": "115/11/23", "fields1": ["今日餘額", "項目"],
                  "data1": [["100,000", "融資金額（仟元）"]]}

        def download(url):
            if "/exchangeReport/" in url:
                return {"stat": "OK", "date": NEW, "tables": [None]}, url
            return legacy, url

        report, url = dated_margin_report(NEW, download)
        self.assertEqual(margin_total(report), 100000)
        self.assertIn("/rwd/", url)

    def test_redirected_payload_must_have_requested_date(self):
        def download(url):
            return self.report(OLD), url.replace("/exchangeReport/", "/rwd/zh/marginTrading/")

        with self.assertRaises(MarginReportError) as error:
            dated_margin_report(NEW, download)
        for attempt in error.exception.attempts:
            self.assertEqual(attempt["status"], "date_mismatch")
            self.assertIn(OLD, attempt["message"])
            self.assertIn("/rwd/", attempt["response_url"])

    def test_http_307_can_follow_twse_report_route_and_rejects_other_targets(self):
        original = "https://www.twse.com.tw/exchangeReport/MI_MARGN"
        official = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
        handler = MarginRedirectHandler()
        response = io.BytesIO()
        request = handler.redirect_request(Request(original), response, 307, "Temporary Redirect", {}, official)
        self.assertEqual(request.full_url, official)
        for target in ("https://www.twse.com.tw/", "http://www.twse.com.tw/exchangeReport/MI_MARGN",
                       "https://example.org/exchangeReport/MI_MARGN"):
            with self.subTest(target=target), self.assertRaises(HTTPError):
                handler.redirect_request(Request(original), response, 307, "Temporary Redirect", {}, target)

        def download(url):
            handler.redirect_request(Request(url), io.BytesIO(), 307, "Temporary Redirect", {},
                                     "https://www.twse.com.tw/")

        with self.assertRaises(MarginReportError) as error:
            dated_margin_report(NEW, download)
        self.assertEqual([a["status"] for a in error.exception.attempts], ["http_redirect", "http_redirect"])

    def test_maintenance_requires_same_day_reconciled_balances_and_reliable_prices(self):
        raw = self.report(NEW, "100")
        raw["tables"][0]["data"].append(["融資(交易單位)", "10"])
        raw["tables"].append({"fields": ["代號", "今日餘額"], "data": [["2330", "10"]]})
        quotes = [{"Code": "2330", "ClosingPrice": "15", "Date": "1151123"}]
        result = maintenance(raw, quotes, NEW)
        self.assertEqual(result["ratio"], 150)
        self.assertTrue(result["price_basis_verified"])
        with self.assertRaisesRegex(ValueError, "margin date not verified"):
            maintenance(raw, quotes, OLD)
        old_quotes = [dict(quotes[0], Date="1151120")]
        with patch("scripts.update_snapshot.dated_maintenance_prices", return_value=old_quotes):
            with self.assertRaisesRegex(ValueError, "historical price share exceeds 0.1%"):
                maintenance(raw, old_quotes, NEW)
        raw["tables"][-1]["data"][0][1] = "9"
        with self.assertRaisesRegex(ValueError, "totals do not reconcile"):
            maintenance(raw, quotes, NEW)
