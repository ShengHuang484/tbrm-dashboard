"""Collect and replay dated TWSE STOCK_DAY evidence for archived close gaps."""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from time import sleep
from urllib.request import Request, urlopen

from scripts.corporate_action_audit import positive

URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
REQUIRED = ("日期", "成交股數", "成交筆數", "收盤價")
NO_CLOSE = {"", "--", "---"}


def source_url(code, month):
    return f"{URL}?response=json&date={month.replace('-', '')}01&stockNo={code}"


def session(value):
    match = re.fullmatch(r"([0-9]{2,3})/([0-9]{2})/([0-9]{2})", value)
    if not match:
        raise ValueError("invalid TWSE ROC session date")
    year, month, day = map(int, match.groups())
    return date(year + 1911, month, day).isoformat()


def report_rows(fields, rows, month):
    if len(fields) != len(set(fields)) or not set(REQUIRED) <= set(fields):
        raise ValueError("TWSE STOCK_DAY field mismatch")
    by_date = {}
    for row in rows:
        record = dict(zip(fields, row, strict=True))
        day = session(record["日期"])
        if day[:7] != month or day in by_date:
            raise ValueError("unexpected or duplicate STOCK_DAY session")
        by_date[day] = (row, record)
    return by_date


def count(value):
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", value):
        raise ValueError("invalid trade count in STOCK_DAY")
    return int(value.replace(",", ""))


def row_status(record):
    raw_close = record["收盤價"].strip()
    volume, trades = (count(record[key]) for key in ("成交股數", "成交筆數"))
    if raw_close not in NO_CLOSE:
        positive(raw_close.replace(",", ""))
        return ("official_close_missing_from_archive" if volume > 0 and trades > 0
                else "inconsistent_activity_counts")
    if volume == trades == 0:
        return "zero_reported_activity"
    if volume > 0 and trades > 0:
        return "activity_without_close"
    return "inconsistent_activity_counts"


def evidence_digest(batch):
    return hashlib.sha256(json.dumps(batch, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def replay_evidence(batches):
    seen = set()
    for batch in batches:
        fields = {k: v for k, v in batch.items() if k != "evidence_sha256"}
        if evidence_digest(fields) != batch["evidence_sha256"]:
            raise ValueError("TWSE gap evidence digest differs")
        code, month = batch["code"], batch["month"]
        if (not re.fullmatch(r"[1-9][0-9]{3}", code)
                or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month)
                or batch["source_url"] != source_url(code, month)
                or not re.fullmatch(r"[0-9a-f]{64}", batch["response_sha256"])):
            raise ValueError("invalid official gap evidence metadata")
        requested = batch["requested_sessions"]
        if requested != sorted(set(requested)) or any(
                date.fromisoformat(d).isoformat() != d or d[:7] != month for d in requested):
            raise ValueError("invalid evidence session scope")
        rows = report_rows(batch["fields"], batch["raw_rows"], month)
        if rows.keys() - set(requested):
            raise ValueError("unexpected selected TWSE evidence row")
        for day in requested:
            if (code, day) in seen:
                raise ValueError("duplicate TWSE gap evidence")
            seen.add((code, day))
            yield (code, day), row_status(rows[day][1]) if day in rows else "official_row_absent"


def capture(code, month, days, body):
    raw = json.loads(body)
    if (raw.get("stat") != "OK" or raw.get("date") != month.replace("-", "") + "01"
            or not re.match(rf"^[0-9]+年[0-9]+月\s+{code}(?:\s|$)", raw.get("title", ""))):
        raise ValueError("TWSE STOCK_DAY report date, code or status differs")
    rows = report_rows(raw["fields"], raw["data"], month)
    if not rows:
        raise ValueError("TWSE STOCK_DAY returned no unambiguous daily rows")
    result = dict(code=code, month=month, source_url=source_url(code, month),
                  report_title=raw["title"], response_sha256=hashlib.sha256(body).hexdigest(),
                  fields=raw["fields"], requested_sessions=sorted(days),
                  raw_rows=[rows[day][0] for day in sorted(days) if day in rows])
    result["evidence_sha256"] = evidence_digest(result)
    list(replay_evidence([result]))
    return result


def collect(queue, market_dates, fetch, priorities, limit, pause):
    targets = defaultdict(set)
    for group in queue:
        if group["priority"] in priorities:
            for day in market_dates:
                if group["first"] <= day <= group["last"]:
                    targets[group["code"], day[:7]].add(day)
    evidence, unavailable = [], []
    for (code, month), days in list(targets.items())[:limit]:
        url = source_url(code, month)
        try:
            evidence.append(capture(code, month, days, fetch(url)))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            unavailable.append(dict(code=code, month=month, source_url=url,
                                    requested_sessions=sorted(days), error=str(exc)[:180]))
        pause()
    return dict(batches=evidence, unavailable=unavailable,
                planned_requests=len(targets), request_limit=limit)


def download(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(request, timeout=12) as response:
        return response.read()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("history", type=Path)
    parser.add_argument("--priority", choices=("critical", "high", "historical"), action="append")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    result = json.loads(args.audit.read_text())
    if result.get("priority_queue_truncated"):
        parser.error("complete audit required")
    if args.limit < 1:
        parser.error("request limit must be positive")
    print(json.dumps(collect(result["unknown_priority_queue"], sorted(json.loads(args.history.read_text())),
                             download, args.priority or ["critical"], args.limit, lambda: sleep(0.8)),
                     ensure_ascii=False, separators=(",", ":")))
