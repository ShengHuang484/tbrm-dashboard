"""Scan pinned exchange reports for subscription reference differences."""
import argparse
import json
from collections import Counter
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.monthly_ex_right_scenario import load_month_reports
from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_listing import listing_windows, listings_on
from scripts.new_low_rights_scenario import ZERO_RIGHTS, select_events
from scripts.twse_corporate_action_parser import roc_date

FIELDS = ("資料日期", "股票代號", "權/息", "除權息前收盤價", "除權息參考價", "減除股利參考價", "開盤競價基準")


def scan_rows(reports, dates, listings):
    windows = listing_windows(listings)
    first, last = dates[0], dates[-1]
    membership = {day: listings_on(windows, day) for day in dates}
    seen = set()
    categories = Counter()
    differences = []
    for month, (payload, url) in reports.items():
        fields = payload["fields"]
        if payload["stat"] != "OK" or len(fields) != len(set(fields)) or not set(FIELDS) <= set(fields):
            raise ValueError(f"unexpected reference-price report: {month}")
        for raw in payload["data"]:
            row = dict(zip(fields, raw, strict=True))
            day, code, kind = roc_date(row[FIELDS[0]]), row[FIELDS[1]], row[FIELDS[2]]
            if not day.startswith(month + "-"):
                raise ValueError(f"reference row outside source month: {day}")
            if not first <= day <= last:
                continue
            key = code, day
            if key in seen:
                raise ValueError(f"duplicate reference-price row: {key}")
            seen.add(key)
            active = membership[day] if day in membership else listings_on(windows, day)
            ordinary = code in active
            scope = "reconstructed_ordinary" if ordinary else "outside_reconstructed_scope"
            prior, official, dividend_only, auction = (
                positive(row[field].replace(",", "")) for field in FIELDS[3:])
            categories[scope, kind] += 1
            if official != dividend_only:
                differences.append(dict(code=code, reported_date=day, scope=scope, exchange_kind=kind,
                        reported_date_is_session=day in membership,
                        prior_close=str(prior), official_reference=str(official),
                        dividend_only_reference=str(dividend_only), auction_basis=str(auction),
                        theoretical_uplift=official > dividend_only, source_url=url))
    return differences, {f"{scope}:{kind}": count for (scope, kind), count in sorted(categories.items())}


def compare(history, report, evidence, archives):
    dates = report["market_dates"]
    if dates != sorted(history):
        raise ValueError("reference scan requires the archived market calendar")
    listings = report["listing_intervals"]
    monthly, hashes = load_month_reports(archives, dates)
    differences, categories = scan_rows(monthly, dates, listings)
    matches = [r for r in differences if (r["code"], r["reported_date"]) ==
               (evidence["code"], evidence["effective_date"])]
    if len(matches) != 1 or any(positive(matches[0][field]) != positive(evidence[field])
            for field in ("prior_close", "official_reference", "dividend_only_reference", "auction_basis")):
        raise ValueError("rights evidence differs from the archived TWSE row")
    cohort = listing_windows(listings)
    ordinary_history = {}
    for day in dates:
        members = listings_on(cohort, day)
        ordinary_history[day] = {code: price for code, price in history[day].items() if code in members}
    altered = select_events(report["applied_events"], ZERO_RIGHTS, evidence)
    scenario = audit_adjusted_lows(ordinary_history, altered, report["lookback"], listings=listings)
    sessions = []
    for before, after in zip(report["sessions"], scenario["sessions"], strict=True):
        if before["date"] != after["date"] or before["eligible_codes"] != after["eligible_codes"]:
            raise ValueError("reference scenario changed the study cohort")
        original, alternative = set(before["adjusted_low_codes"]), set(after["adjusted_low_codes"])
        sessions.append(dict(date=before["date"], eligible=len(before["eligible_codes"]),
                             twse_reference=len(original), zero_rights=len(alternative),
                             added=sorted(alternative - original), removed=sorted(original - alternative)))
    return dict(month_sha256=hashes, row_counts=categories, reference_differences=differences,
                research_factor_counts=dict(sorted(Counter(
                    row["event_type"] for row in report["applied_events"]).items())),
                sessions=sessions, other_differences_require_event_evidence=True,
                market_baseline_verified=False, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("history", "report", "evidence"):
        parser.add_argument(field, type=Path)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(*(json.loads(p.read_bytes()) for p in (args.history, args.report, args.evidence)),
                             args.archives), ensure_ascii=False, indent=2))
