"""Validate the scheduled market session and publish only a usable snapshot."""
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from time import sleep
from zoneinfo import ZoneInfo

from scripts import update_snapshot

TAIPEI = ZoneInfo("Asia/Taipei")
CLOSE = time(13, 30)
MARKET_REPORT = "https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date="
DAILY_STOCK_REPORT = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999&date="
DAILY_FIELDS = {
    "證券代號": "Code", "證券名稱": "Name", "成交股數": "TradeVolume",
    "成交金額": "TradeValue", "開盤價": "OpeningPrice", "最高價": "HighestPrice",
    "最低價": "LowestPrice", "收盤價": "ClosingPrice", "成交筆數": "Transaction",
}
FILE_DATES = {
    "twse_dated_breadth": (None, "date"),
    "taifex_vix": (None, "date"),
    "margin_maintenance": (None, "date"),
    "twse_dated_margin": ("latest", "date"),
    "taifex_putcall": ("latest", "Date"),
    "tpex_index": ("latest", "Date"),
    "breadth_history": ("latest", "date"),
    "futures_history": ("latest", "date"),
    "twse_foreign": (None, "date"),
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def market_date(value):
    digits = str(value).replace("/", "").replace("-", "")
    if len(digits) == 7 and digits.isascii() and digits.isdigit():
        digits = str(int(digits[:3]) + 1911) + digits[3:]
    if len(digits) != 8 or not digits.isascii() or not digits.isdigit():
        raise ValueError(f"unrecognized market date: {value}")
    return date.fromisoformat(digits).isoformat()


def expected_session(now, calendar):
    local = now.astimezone(TAIPEI)
    day = local.date() - timedelta(days=local.time() < CLOSE)
    for _ in range(31):
        year = calendar["years"].get(str(day.year))
        if year is None:
            raise ValueError(f"TWSE calendar not available for {day.year}")
        if day.weekday() < 5 and day.isoformat() not in year["closed"]:
            return day.isoformat()
        day -= timedelta(days=1)
    raise ValueError("no expected trading session in calendar")


def check_report(report, target):
    if report.get("stat") != "OK":
        raise ValueError("TWSE market report is not ready")
    fields = report["fields"]
    date_column = fields.index("日期")
    close_column = fields.index("發行量加權股價指數")
    sessions = {}
    for row in report["data"]:
        day = market_date(row[date_column])
        value = float(str(row[close_column]).replace(",", ""))
        if day[:7] != target[:7] or day in sessions or not 0 < value < float("inf"):
            raise ValueError("TWSE market report contains invalid or duplicate sessions")
        sessions[day] = value
    if target not in sessions:
        raise ValueError(f"TWSE report has not verified {target}; latest={max(sessions, default=None)}")
    return sessions[target]


def stock_session(stocks):
    if not isinstance(stocks, list) or not stocks:
        raise ValueError("TWSE stock snapshot is empty")
    dates = {market_date(row["Date"]) for row in stocks}
    if len(dates) != 1:
        raise ValueError("TWSE stock snapshot has mixed dates")
    return dates.pop()


def dated_stock_snapshot(report, target):
    if report.get("stat") != "OK" or market_date(report["date"]) != target:
        raise ValueError("dated TWSE stock report does not match expected session")
    required = {*DAILY_FIELDS, "漲跌(+/-)", "漲跌價差"}
    tables = [table for table in report["tables"] if required <= set(table.get("fields", []))]
    if len(tables) != 1:
        raise ValueError("expected one complete dated TWSE stock table")
    table, = tables
    records = {}
    roc = str(int(target[:4]) - 1911) + target[5:7] + target[8:10]
    for row in table["data"]:
        fields = dict(zip(table["fields"], row, strict=True))
        mapped = {key: str(fields[field]).strip().replace(",", "") if key not in ("Code", "Name")
                  else str(fields[field]).strip() for field, key in DAILY_FIELDS.items()}
        code = mapped["Code"]
        if not code or code in records:
            raise ValueError(f"invalid or duplicate stock code: {code}")
        sign = re.sub(r"<[^>]+>", "", str(fields["漲跌(+/-)"])).strip()
        magnitude = str(fields["漲跌價差"]).replace(",", "").strip()
        if not re.fullmatch(r"\d+(?:\.\d+)?", magnitude):
            change = "--"
        elif sign in ("+", "-"):
            change = sign + magnitude
        else:
            change = "0" if sign == "" and float(magnitude) == 0 else "--"
        records[code] = dict(mapped, Date=roc, Change=change)
    valid_closes = 0
    for code, row in records.items():
        if re.fullmatch(r"[1-9]\d{3}", code):
            try:
                valid_closes += 0 < float(row["ClosingPrice"]) < float("inf")
            except ValueError:
                continue
    if valid_closes < 500:
        raise ValueError("dated TWSE stock report has fewer than 500 valid four-digit closes")
    return list(records.values())


def validate_core(staging, target, close):
    manifest = read(staging / "manifest.json")
    for source in ("twse_stocks", "index_history"):
        if manifest["sources"].get(source, {}).get("status") != "ok":
            raise ValueError(f"{source} did not complete")
    snapshot = read(staging / "index_history.json")
    rows = snapshot["rows"]
    dates = [r["date"] for r in rows]
    if (len(dates) < 252 or dates != sorted(set(dates)) or dates[-1] != target
            or snapshot["date"] != target or manifest["sources"]["index_history"]["date"] != target
            or rows[-1]["close"] != close
            or any(market_date(d) != d or not 0 < r["close"] < float("inf")
                   for d, r in zip(dates, rows))):
        raise ValueError("index history does not match the verified official session")
    if stock_session(read(staging / "twse_stocks.json")) != target:
        raise ValueError("stored stock snapshot does not match the expected session")
    return manifest


def source_warnings(staging, manifest, target):
    warnings = {key: str(value)[:240] for key, value in manifest.get("errors", {}).items()}
    if manifest["sources"].get("futures_history", {}).get("status") == "ok":
        warnings.pop("taifex_futures", None)
    for key, (shape, field) in FILE_DATES.items():
        try:
            rows = read(staging / (key + ".json"))
            actual = (max(market_date(row[field]) for row in rows)
                      if shape == "latest" else market_date(rows[field]))
            if actual != target:
                warnings.setdefault(key, f"來源日期 {actual}，預期 {target}")
        except (OSError, ValueError, KeyError, TypeError):
            warnings.setdefault(key, "尚未取得有效資料日期")
    for key, value in manifest["sources"].items():
        if value.get("status") == "partial":
            if key == "twse_dated_margin" and target in value.get("errors", {}):
                warnings[key] = str(value["errors"][target])[:240]
            warnings.setdefault(key, f"歷史資料缺漏 {', '.join(value.get('missing', []))}")
    return warnings


def refresh(data_dir, now, *, fetch=update_snapshot.fetch, update=update_snapshot.main,
            retry_delays=(30, 60), pause=sleep):
    try:
        previous = read(data_dir / "index_history.json")["date"]
    except (OSError, ValueError, KeyError):
        previous = None
    status = dict(checked_at=now.astimezone(timezone.utc).isoformat(),
                  expected_session=None, last_valid_session=previous, status="STALE",
                  download_status="not_started", date_valid=False, warnings={})
    target = None
    try:
        target = expected_session(now, read(data_dir / "market_calendar.json"))
        status["expected_session"] = target
        for delay in (*retry_delays, None):
            try:
                report = fetch(MARKET_REPORT + target.replace("-", ""))
                close = check_report(report, target)
                stock_url = update_snapshot.ENDPOINTS["twse_stocks"]
                try:
                    stocks = fetch(stock_url)
                    actual = stock_session(stocks)
                    status["source_stock_session"] = actual
                    if actual != target:
                        raise ValueError(f"STOCK_DAY_ALL {actual}; expected {target}")
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    status["warnings"]["stock_openapi"] = str(exc)[:240]
                    stock_url = DAILY_STOCK_REPORT + target.replace("-", "")
                    stocks = dated_stock_snapshot(fetch(stock_url), target)
                status["published_stock_source"] = stock_url
                break
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if delay is None:
                    raise
                print(f"TWSE not ready ({exc}); retry in {delay}s", flush=True)
                pause(delay)

        if previous is not None and target < previous:
            raise ValueError(f"refusing to replace {previous} with older session {target}")
        status["download_status"] = "core_downloaded"
        with TemporaryDirectory(prefix="tbrm-market-") as temp:
            staging = Path(temp) / "data"
            copytree(data_dir, staging)
            update(staging, stocks)
            manifest = validate_core(staging, target, close)
            manifest["sources"]["twse_stocks"].update(date=target, url=stock_url)
            (staging / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            warnings = source_warnings(staging, manifest, target)
            # A failed retry must not remove a valid same-session external source.
            if previous == target and warnings:
                prior_warnings = source_warnings(data_dir, read(data_dir / "manifest.json"), target)
                if warnings.keys() - prior_warnings.keys():
                    status.update(status="PARTIAL", date_valid=True, warnings=status["warnings"] | warnings,
                                  download_status="rejected_regression")
                    return status
            copytree(staging, data_dir, dirs_exist_ok=True)
        status.update(status="PARTIAL" if warnings else "VALID", date_valid=True,
                      last_valid_session=target, warnings=status["warnings"] | warnings,
                      download_status="partial" if warnings else "complete")
    except (OSError, ValueError, KeyError, TypeError, SystemExit) as exc:
        status["warnings"]["market_refresh"] = str(exc)[:350]
        if target == previous and target is not None:
            # A transport failure does not invalidate a close already verified for this session.
            try:
                published = read(data_dir / "market_update_status.json")
                if not published["date_valid"] or published["last_valid_session"] != target:
                    raise ValueError("there is no previously verified close for this session")
                close = read(data_dir / "index_history.json")["rows"][-1]["close"]
                manifest = validate_core(data_dir, target, close)
                pending = source_warnings(data_dir, manifest, target)
                status.update(status="PARTIAL" if pending else "VALID", date_valid=True,
                              download_status="retained_verified", warnings=status["warnings"] | pending)
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                pass
    return status


def main():
    folder = update_snapshot.ROOT / "data"
    status = refresh(folder, datetime.now(timezone.utc))
    path = folder / "market_update_status.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(json.dumps(status, ensure_ascii=False))
    for source, message in status["warnings"].items():
        safe = (source + " " + message).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::warning title=Market data::{safe}")
    return status


if __name__ == "__main__":
    main()
