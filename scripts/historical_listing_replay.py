"""Replay research using a bounded listing reconstruction with dated exit evidence."""
import argparse
import csv
import json
from pathlib import Path

from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_listing import listing_windows, listings_on
from scripts.new_low_replay_check import membership_digest


def replay(history, adjusted, roster, evidence, *, strict_report=False):
    dates = sorted(history)
    if evidence["snapshot_date"] < dates[-1]:
        raise ValueError("snapshot predates research endpoint")
    if len({row["code"] for row in roster}) != len(roster):
        raise ValueError("duplicate snapshot code")
    receipts = {row["code"] for row in roster if row["industry"] == "91"}
    listings = [dict(code=row["code"], listed_from=row["listed_from"], delisted_on=None)
                for row in roster if row["code"] not in receipts]
    exits = evidence["historical_exits"]
    if any(not all(row.get(k, "").startswith("https://")
                   for k in ("listing_source", "exit_source")) for row in exits):
        raise ValueError("historical exits require listing and exit sources")
    listings.extend(exits)
    windows = listing_windows(listings)
    ordinary = {day: {code: close for code, close in quotes.items() if code not in receipts}
                for day, quotes in history.items()}
    events = [row for row in adjusted["applied_events"] if row["code"] not in receipts]
    conflicts = {}
    for day, quotes in ordinary.items():
        outside = sorted(quotes.keys() - listings_on(windows, day).keys())
        if outside:
            conflicts[day] = outside
    if conflicts:
        if strict_report:
            raise ValueError(f"quotes outside reconstructed listing intervals: {conflicts}")
        return dict(outside_listing_quotes=conflicts, listing_universe_verified=False,
                    score_eligible=False)
    result = audit_adjusted_lows(ordinary, events, adjusted["lookback"], listings=listings)
    if strict_report:
        result.update(applied_events=events, issuer_snapshot_date=evidence["snapshot_date"],
                      historical_exit_codes=sorted({row["code"] for row in exits}))
        return result
    return dict(snapshot_date=evidence["snapshot_date"], market_sessions=len(dates),
                historical_exit_codes=sorted({row["code"] for row in exits}),
                factor_count=result["factor_count"], outside_listing_quotes={},
                sessions=[dict(date=row["date"], eligible=row["strict_eligible"],
                               lows=row["adjusted_low_count"], active=row["active_listings"],
                               unquoted_current=row["unquoted_current_listings"],
                               membership_sha256=membership_digest(row))
                          for row in result["sessions"]],
                listing_universe_verified=False, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "adjusted", "roster", "evidence"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--strict-report", action="store_true")
    args = parser.parse_args()
    with args.roster.open(newline="") as roster:
        result = replay(json.loads(args.history.read_text()), json.loads(args.adjusted.read_text()),
                        list(csv.DictReader(roster)), json.loads(args.evidence.read_text()),
                        strict_report=args.strict_report)
    print(json.dumps(result, indent=2))
