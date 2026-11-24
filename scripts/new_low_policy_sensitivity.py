"""Compare 252 market sessions with the latest 252 observed closes."""
import argparse
import json
from pathlib import Path

from scripts.new_low_adjusted_audit import OBSERVED_QUOTES, audit_adjusted_lows


def compare_policies(history, events, lookback=252, *, listings=None):
    events = list(events)
    strict = audit_adjusted_lows(history, events, lookback, listings=listings)
    observed = audit_adjusted_lows(history, events, lookback, listings=listings,
                                  quote_policy=OBSERVED_QUOTES)
    results = []
    for a, b in zip(strict["sessions"], observed["sessions"], strict=True):
        strict_codes, observed_codes = set(a["eligible_codes"]), set(b["eligible_codes"])
        strict_lows, observed_lows = set(a["adjusted_low_codes"]), set(b["adjusted_low_codes"])
        if not strict_codes <= observed_codes or strict_lows != observed_lows & strict_codes:
            raise ValueError("observed policy changes the common continuous cohort")
        new_codes = observed_codes - strict_codes
        results.append({
            "date": a["date"],
            "strict_eligible_count": len(strict_codes),
            "observed_eligible_count": len(observed_codes),
            "strict_raw_low_count": a["raw_low_count"],
            "observed_raw_low_count": b["raw_low_count"],
            "strict_adjusted_low_count": len(strict_lows),
            "observed_adjusted_low_count": len(observed_lows),
            "additional_eligible_codes": sorted(new_codes),
            "additional_adjusted_low_codes": sorted(observed_lows & new_codes),
        })
    return {"lookback": lookback, "factor_count": strict["factor_count"],
            "sessions": results, "research_only": True, "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("action_report", type=Path)
    parser.add_argument("--listings", type=Path)
    args = parser.parse_args()
    history = json.loads(args.history.read_text())
    report = json.loads(args.action_report.read_text())
    listings = json.loads(args.listings.read_text()) if args.listings else None
    print(json.dumps(compare_policies(history, report["applied_events"], listings=listings), indent=2))
