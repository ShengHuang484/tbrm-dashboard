"""Cross-check archived quotes against a dated TWSE issuer snapshot."""
import argparse
import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path

from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_policy_sensitivity import compare_policies

URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
FIELDS = ("code", "listed_from", "industry")


def snapshot(raw):
    rows = json.loads(raw)
    stamps = {r["出表日期"] for r in rows}
    if len(stamps) != 1:
        raise ValueError("issuer snapshot must have one report date")
    roc, = stamps
    stamp = date.fromisoformat(str(int(roc[:-4]) + 1911) + roc[-4:]).isoformat()
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FIELDS)
    seen = set()
    for r in sorted(rows, key=lambda r: r["公司代號"]):
        code = r["公司代號"]
        if not code.isascii() or not code.isdigit() or code in seen:
            raise ValueError("invalid or duplicate issuer code")
        seen.add(code)
        listed = date.fromisoformat(r["上市日期"]).isoformat()
        if (r["產業別"] == "91") != r["公司簡稱"].endswith("-DR"):
            raise ValueError(f"conflicting TDR evidence: {code}")
        writer.writerow((code, listed, r["產業別"]))
    return output.getvalue(), dict(source_url=URL, snapshot_date=stamp,
                                   raw_sha256=hashlib.sha256(raw).hexdigest())


def reconcile(history, events, records, snapshot_date, lookback=252, *, strict_report=False):
    first, last = min(history), max(history)
    if snapshot_date < last:
        raise ValueError("issuer snapshot precedes research endpoint")
    by_code = {r["code"]: r for r in records}
    if not records or len(by_code) != len(records):
        raise ValueError("empty or duplicate issuer roster")
    quoted = set().union(*(prices.keys() for prices in history.values()))
    receipts = {r["code"] for r in records if r["industry"] == "91" and r["code"] in quoted}
    # Only exclude while the listed receipt actually exists. Earlier uses of its code need review.
    def receipt(code, day):
        return code in receipts and by_code[code]["listed_from"] <= day

    prices = {d: {c: p for c, p in row.items() if not receipt(c, d)} for d, row in history.items()}
    retained = [e for e in events if not receipt(e["code"], e["ex_date"])]
    if strict_report:
        report = audit_adjusted_lows(prices, retained, lookback)
        report.update(issuer_snapshot_date=snapshot_date, applied_events=retained,
                      excluded_receipt_codes=sorted(receipts))
        return report
    policies = compare_policies(prices, retained, lookback)
    endpoint_ordinary = {c for c,r in by_code.items() if r["industry"] != "91"
                         and r["listed_from"] <= last and len(c) == 4}
    first_quotes = {}
    for day in sorted(history):
        for code in history[day]:
            first_quotes.setdefault(code, day)
    return dict(snapshot_date=snapshot_date, window=[first,last], source_issuer_count=len(records),
                quoted_receipt_codes=sorted(receipts), history_only_codes=sorted(quoted - by_code.keys()),
                quotes_before_snapshot_listing={c:d for c,d in first_quotes.items()
                    if c in by_code and d < by_code[c]["listed_from"]},
                endpoint_roster_without_close=sorted(endpoint_ordinary - history[last].keys()),
                excluded_receipt_events=[(e["code"], e["ex_date"]) for e in events if receipt(e["code"],e["ex_date"])],
                sessions=policies["sessions"], factor_count=policies["factor_count"],
                listing_universe_verified=False, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract")
    extract.add_argument("raw", type=Path)
    extract.add_argument("csv", type=Path)
    run = commands.add_parser("compare")
    for name in ("history", "action_report", "csv"):
        run.add_argument(name, type=Path)
    run.add_argument("snapshot_date")
    run.add_argument("--strict-report", action="store_true")
    args = parser.parse_args()
    if args.command == "extract":
        data, result = snapshot(args.raw.read_bytes())
        args.csv.write_text(data)
    else:
        result = reconcile(json.loads(args.history.read_text()), json.loads(
            args.action_report.read_text())["applied_events"], list(csv.DictReader(
                io.StringIO(args.csv.read_text()))), args.snapshot_date,
            strict_report=args.strict_report)
    print(json.dumps(result, indent=2))
