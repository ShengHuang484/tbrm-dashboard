"""Replay unresolved listing-start candidates against the archived new-low window."""

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from scripts.new_low_adjusted_audit import STRICT_SESSIONS, audit_adjusted_lows
from scripts.new_low_listing import listing_windows


def audit(checkpoint, review):
    cases = {row["code"]: row for row in review["listing_start_differences"]
             if row["status"] == "REVIEW"}
    listings = checkpoint["listing_intervals"]
    present = {row["code"] for row in listings if row["code"] in cases
               and row["listed_from"] == cases[row["code"]]["archived"]}
    if not cases or present != cases.keys():
        raise ValueError("each disputed listing start must match the archive")
    candidate = [
        dict(row, listed_from=cases[row["code"]]["isin"])
        if row["code"] in cases and row["listed_from"] == cases[row["code"]]["archived"]
        else row
        for row in listings
    ]
    history, events, lookback = (checkpoint[key] for key in ("history", "applied_events", "lookback"))
    dates = sorted(history)
    if not 1 <= lookback < len(dates):
        raise ValueError("insufficient market sessions")

    first = date.fromisoformat(dates[0]).isoformat()
    end = (date.fromisoformat(dates[-1]) + timedelta(days=1)).isoformat()

    def clipped_windows(records, code):
        return [
            (max(start, first), min(stop or end, end))
            for start, stop in records.get(code, ())
            if max(start, first) < min(stop or end, end)
        ]

    old_windows = listing_windows(listings)
    new_windows = listing_windows(candidate)
    results = {
        code: dict(archived=case["archived"], candidate=case["isin"],
                   clamped_intervals_equal=clipped_windows(old_windows, code) == clipped_windows(new_windows, code),
                   eligibility_changed_sessions=[], adjusted_low_membership_changed_sessions=[])
        for code, case in sorted(cases.items())
    }
    changed = []
    method = "archive_boundary_proof"
    if not all(row["clamped_intervals_equal"] for row in results.values()):
        method = "strict_replay"
        original = audit_adjusted_lows(history, events, lookback, listings=listings)
        scenario = audit_adjusted_lows(history, events, lookback, listings=candidate)
        comparisons = list(zip(original["sessions"], scenario["sessions"], strict=True))
        fields = ("eligible_codes", "adjusted_low_codes", "raw_low_count", "adjusted_low_count")
        changed = [a["date"] for a, b in comparisons if any(a[key] != b[key] for key in fields)]
        for code, result in results.items():
            for field, output in (("eligible_codes", "eligibility_changed_sessions"),
                                  ("adjusted_low_codes", "adjusted_low_membership_changed_sessions")):
                result[output] = [a["date"] for a, b in comparisons
                                  if (code in a[field]) != (code in b[field])]

    return dict(lookback=lookback, quote_policy=STRICT_SESSIONS, method=method,
                archive_sessions=len(dates), earliest_window_session=first,
                first_evaluated_session=dates[lookback], last_evaluated_session=dates[-1],
                evaluated_sessions=len(dates) - lookback, cases=results,
                changed_market_sessions=changed,
                committed_listing_changes=False, score_eligible=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("review", type=Path)
    args = parser.parse_args()
    checkpoint = args.checkpoint.read_bytes()
    review = args.review.read_bytes()
    result = audit(json.loads(checkpoint), json.loads(review))
    result["checkpoint_sha256"] = hashlib.sha256(checkpoint).hexdigest()
    result["review_sha256"] = hashlib.sha256(review).hexdigest()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
