"""Download TWSE monthly TWT49U JSON into a research-only raw archive.

Usage:
  python -m scripts.twse_event_download --start 2025-11 --end 2026-11 --out data/research/twse_events

Raw responses are retained unchanged. No automatic event verification, price
adjustment, or scoring is performed. Unexpected responses fail closed.
"""
import argparse
import hashlib
import json
import re
import time
from datetime import date
from calendar import monthrange
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"


def months_between(start, end):
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    date(sy, sm, 1)
    date(ey, em, 1)
    if (sy, sm) > (ey, em):
        raise ValueError("start after end")
    while (sy, sm) <= (ey, em):
        yield f"{sy:04d}-{sm:02d}"
        sm += 1
        if sm == 13:
            sy, sm = sy + 1, 1


def fetch_month(month, opener=urlopen):
    year, mon = map(int, month.split("-"))
    first = f"{year:04d}{mon:02d}01"
    last = f"{year:04d}{mon:02d}{monthrange(year, mon)[1]:02d}"
    url = BASE + "?" + urlencode({"response": "json", "startDate": first, "endDate": last})
    request = Request(url, headers={"User-Agent": "TBRM-research/1.0", "Accept": "application/json"})
    with opener(request, timeout=25) as response:
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("response exceeds limit")
    obj = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("unexpected TWSE response")
    # A successful HTTP request does not guarantee valid historical data.
    # Preserve the raw response for manual schema and coverage review.
    if obj.get("stat") != "OK":
        raise ValueError("TWSE did not confirm success: " + str(obj.get("stat"))[:100])
    if not isinstance(obj.get("data"), list) and not isinstance(obj.get("tables"), list):
        raise ValueError("missing TWSE tabular payload")
    return url, raw, obj


def archive(start, end, out_dir, fetcher=fetch_month):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for month in months_between(start, end):
        try:
            url, raw, obj = fetcher(month)
            # Reject a successful response if its event dates belong to other months.
            tables = obj.get("tables") if isinstance(obj.get("tables"), list) else [obj]
            observed = []
            for table in tables:
                if not isinstance(table, dict):
                    continue
                fields = table.get("fields", [])
                rows = table.get("data", [])
                if not isinstance(fields, list) or not isinstance(rows, list):
                    continue
                if "資料日期" not in fields:
                    continue
                idx = fields.index("資料日期")
                for row in rows:
                    if not isinstance(row, list) or idx >= len(row):
                        raise ValueError("malformed event date row")
                    raw_date = str(row[idx]).strip()
                    match = re.fullmatch(r"(\d{2,4})年(\d{1,2})月(\d{1,2})日", raw_date)
                    if match:
                        y, m, d = map(int, match.groups())
                        if y < 1911:
                            y += 1911
                        date(y, m, d)
                        digits = f"{y:04d}{m:02d}{d:02d}"
                    else:
                        digits = raw_date.replace("/", "").replace("-", "")
                    if not digits.isdigit() or len(digits) not in (7, 8):
                        raise ValueError("unrecognized event date: " + raw_date[:30])
                    if len(digits) == 7:
                        digits = str(int(digits[:3]) + 1911) + digits[3:]
                    date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
                    if digits[:6] != month.replace("-", ""):
                        raise ValueError("event outside requested month: " + raw_date[:30])
                    observed.append(digits)
            if not observed:
                raise ValueError("no dated events to establish month coverage")
            filename = month + ".json"
            (out / filename).write_bytes(raw)
            entries.append({"month": month, "status": "downloaded_unverified",
                            "file": filename, "source_url": url,
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "twse_status": obj.get("stat"),
                            "bytes": len(raw), "dated_rows": len(observed),
                            "first_event_date": min(observed), "last_event_date": max(observed)})
        except Exception as exc:
            entries.append({"month": month, "status": "failed",
                            "error": type(exc).__name__ + ": " + str(exc)[:180]})
        time.sleep(0.5)
    report = {"start_month": start, "end_month": end, "entries": entries,
              "successful_months": [e["month"] for e in entries if e["status"] == "downloaded_unverified"],
              "failed_months": [e["month"] for e in entries if e["status"] == "failed"],
              "corporate_action_completeness_verified": False,
              "score_eligible": False}
    (out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="YYYY-MM")
    p.add_argument("--end", required=True, help="YYYY-MM")
    p.add_argument("--out", default="data/research/twse_events")
    args = p.parse_args()
    report = archive(args.start, args.end, args.out)
    print(json.dumps({"successful_months": len(report["successful_months"]),
                      "failed_months": report["failed_months"], "score_eligible": False}, ensure_ascii=False))
    if report["failed_months"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
