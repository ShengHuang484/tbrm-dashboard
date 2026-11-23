"""Validate event transitions and delisted security boundaries."""
import argparse
import json
from fractions import Fraction
from pathlib import Path

from scripts.corporate_action_audit import positive


def compare_transition(history, sample):
    """Compare adjusted returns allowing for each published close's rounding.

    An overall rescaling of an external adjusted series cancels in the ratio.
    The sample must span only the action whose reference is supplied.
    """
    code, before, after = (sample[key] for key in ("code", "before_date", "effective_date"))
    if before >= after or not sample["source_url"].startswith("https://"):
        raise ValueError("invalid external transition provenance")
    if (max((day for day in history if day < after and code in history[day]), default=None)
            != before):
        raise ValueError("transition must use the last pre-event trading close")
    raw_after = Fraction(positive(history[after][code]))
    reference = Fraction(positive(sample["reference"]))
    expected = raw_after / reference
    before_adjusted = Fraction(positive(sample["external_before"]))
    after_adjusted = Fraction(positive(sample["external_after"]))
    half_step = Fraction(positive(sample["display_step"])) / 2
    if min(before_adjusted, after_adjusted) <= half_step:
        raise ValueError("external price resolution too coarse")
    lower = (after_adjusted - half_step) / (before_adjusted + half_step)
    upper = (after_adjusted + half_step) / (before_adjusted - half_step)
    return {
        "code": code, "effective_date": after, "expected_ratio": str(expected),
        "external_ratio_interval": [str(lower), str(upper)],
        "agrees_with_display_precision": lower <= expected <= upper,
    }


def audit_delistings(history, records):
    reports = []
    for event in records:
        code, day = event["code"], event["delisted_on"]
        dates = sorted(d for d, prices in history.items() if code in prices)
        reports.append({
            "code": code, "delisted_on": day,
            "last_pre_delisting_close_date": max((d for d in dates if d < day), default=None),
            "post_boundary_quote_dates": [d for d in dates if d >= day],
            "successor": event.get("successor"),
            "carry_history_to_successor": False,
        })
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    history = json.loads(args.history.read_text())
    evidence = json.loads(args.evidence.read_text())
    print(json.dumps({
        "external_transitions": [compare_transition(history, row) for row in evidence["transitions"]],
        "delistings": audit_delistings(history, evidence["delistings"]),
        "market_baseline_verified": False, "score_eligible": False,
    }, indent=2))
