"""Bounded, research-only independent TWSE quote cross-check for missing closes.

The official MI_INDEX stock detail is checked for a selected trading date.
Absence from a report does not prove suspension or delisting.
"""
import json
import re
import urllib.request
from pathlib import Path


def plain(value):
    return re.sub(r"<[^>]*>", "", str(value)).strip()


def stock_rows(payload):
    tables = payload.get("tables", [])
    if not isinstance(tables, list):
        tables = []
    for suffix in ("", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        fields, rows = payload.get("fields" + suffix), payload.get("data" + suffix)
        if isinstance(fields, list) and isinstance(rows, list):
            tables.append({"fields": fields, "data": rows})
    result = {}
    for table in tables:
        if not isinstance(table, dict):
            continue
        fields = [plain(x).replace(" ", "") for x in table.get("fields", [])]
        code_col = next((i for i, x in enumerate(fields) if "證券代號" in x or "股票代號" in x), None)
        close_col = next((i for i, x in enumerate(fields) if "收盤價" in x or x == "收盤"), None)
        if code_col is None or close_col is None:
            continue
        for row in table.get("data", []):
            if not isinstance(row, list) or max(code_col, close_col) >= len(row):
                continue
            code = plain(row[code_col])
            if re.fullmatch(r"[1-9][0-9]{3}", code):
                result[code] = plain(row[close_col])
    return result


def crosscheck(history, audit, fetcher, max_dates=12):
    gaps = {}
    for item in audit["internal_gap_details"]:
        for day in item["internal_missing_dates"]:
            gaps.setdefault(day, []).append(item["code"])
    # Highest missing-stock concentration first, bounded to avoid heavy API traffic.
    selected = sorted(gaps, key=lambda day: (-len(gaps[day]), day))[:max_dates]
    checks = []
    for day in selected:
        url = ("https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date="
               + day.replace("-", "") + "&type=ALLBUT0999")
        try:
            payload = fetcher(url)
            if payload.get("stat") != "OK":
                raise ValueError("TWSE report status not OK")
            reported = str(payload.get("date", "")).replace("/", "")
            if reported and reported not in (day.replace("-", ""),):
                raise ValueError("TWSE report date mismatch")
            quotes = stock_rows(payload)
            if not quotes:
                raise ValueError("stock detail table not recognized")
            for code in sorted(gaps[day]):
                value = quotes.get(code)
                checks.append({
                    "date": day, "code": code, "source_url": url,
                    "status": ("official_quote_present_missing_in_archive"
                               if value is not None and value not in ("", "--", "---", "X")
                               else "official_row_no_valid_close" if value is not None
                               else "not_found_in_official_detail"),
                    "official_close_raw": value,
                    "independent_cause_verified": False,
                })
        except Exception as exc:
            for code in sorted(gaps[day]):
                checks.append({"date": day, "code": code, "source_url": url,
                               "status": "official_source_unavailable",
                               "error": str(exc)[:180],
                               "independent_cause_verified": False})
    return {
        "checked_dates": selected,
        "total_internal_gap_dates": len(gaps),
        "checks": checks,
        "archive_missing_but_official_quote_present": sum(
            x["status"] == "official_quote_present_missing_in_archive" for x in checks),
        "official_source_unavailable": sum(
            x["status"] == "official_source_unavailable" for x in checks),
        "remaining_dates_unchecked": len(gaps) - len(selected),
        "all_gaps_verified": False,
        "score_eligible": False,
    }


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("history", type=Path)
    parser.add_argument("universe_audit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = crosscheck(json.loads(args.history.read_text()),
                        json.loads(args.universe_audit.read_text()), fetch)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False))
