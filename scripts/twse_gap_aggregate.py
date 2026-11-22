"""Aggregate independent TWSE missing-quote audits without treating absence as suspension."""
import json
from collections import Counter
from pathlib import Path


def aggregate(reports, expected_total_dates):
    seen = set()
    checks = []
    for report in reports:
        for day in report["checked_dates"]:
            if day in seen:
                raise ValueError("overlapping audit date: " + day)
            seen.add(day)
        checks.extend(report["checks"])
    if any(x["date"] not in seen for x in checks):
        raise ValueError("check date not listed in batch")
    counts = dict(sorted(Counter(x["status"] for x in checks).items()))
    return {
        "unique_dates_checked": len(seen),
        "expected_total_internal_gap_dates": expected_total_dates,
        "dates_remaining": expected_total_dates - len(seen),
        "stock_date_pairs_checked": len(checks),
        "status_counts": counts,
        "official_quotes_missing_from_archive": counts.get("official_quote_present_missing_in_archive", 0),
        "source_unavailable": counts.get("official_source_unavailable", 0),
        "all_dates_checked": len(seen) == expected_total_dates,
        "absence_proves_suspension": False,
        "score_eligible": False,
    }


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1])
    files = sorted(root.glob("official_quote_gap_crosscheck*.json"))
    if not files:
        raise SystemExit("No official quote gap crosschecks found")
    reports = [json.loads(f.read_text()) for f in files]
    expected = reports[0]["total_internal_gap_dates"]
    if any(r["total_internal_gap_dates"] != expected for r in reports):
        raise SystemExit("Inconsistent total date count")
    result = aggregate(reports, expected)
    (root / "official_quote_gap_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    if result["dates_remaining"] < 0:
        raise SystemExit("More checked dates than expected")
