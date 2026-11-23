"""Replay unresolved listing-start candidates against the archived new-low window."""

import argparse
import hashlib
import json
from pathlib import Path

from scripts.new_low_adjusted_audit import audit_adjusted_lows


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
    original = audit_adjusted_lows(history, events, lookback, listings=listings)
    scenario = audit_adjusted_lows(history, events, lookback, listings=candidate)
    comparisons = list(zip(original["sessions"], scenario["sessions"], strict=True))
    fields = ("eligible_codes", "adjusted_low_codes", "raw_low_count", "adjusted_low_count")
    results = {}
    for code, case in sorted(cases.items()):
        results[code] = dict(archived=case["archived"], candidate=case["isin"],
                             eligibility_changed_sessions=[
                                 a["date"] for a, b in comparisons
                                 if (code in a["eligible_codes"]) != (code in b["eligible_codes"])],
                             adjusted_low_membership_changed_sessions=[
                                 a["date"] for a, b in comparisons
                                 if (code in a["adjusted_low_codes"]) != (code in b["adjusted_low_codes"])])
    return dict(lookback=lookback, quote_policy=original["quote_policy"],
                earliest_window_session=original["market_dates"][0],
                first_evaluated_session=comparisons[0][0]["date"],
                last_evaluated_session=comparisons[-1][0]["date"],
                evaluated_sessions=len(comparisons), cases=results,
                changed_market_sessions=[a["date"] for a, b in comparisons
                                         if any(a[key] != b[key] for key in fields)],
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
