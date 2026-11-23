"""Audit one eligible stock against provider closes over the actual research window."""
import argparse
import json
from fractions import Fraction
from pathlib import Path

from scripts.corporate_action_audit import event_factors, positive
from scripts.new_low_adjusted_audit import STRICT_SESSIONS


def check_window(history, report, baseline, code, day, display_step):
    dates = report["market_dates"]
    if (dates != sorted(history) or baseline["market_dates"] != dates
            or report["quote_policy"] != STRICT_SESSIONS):
        raise ValueError("sample requires the same strict market calendar")
    session = next(r for r in report["sessions"] if r["date"] == day)
    if code not in session["eligible_codes"]:
        raise ValueError("sample is outside the local strict cohort")
    end = dates.index(day)
    window = dates[end - report["lookback"]:end + 1]
    if len(window) != report["lookback"] + 1:
        raise ValueError("short local window")
    quotes = baseline["adjusted_closes"]
    anchor = Fraction(positive(quotes[day][code]))
    half = Fraction(positive(display_step)) / 2
    if anchor <= half:
        raise ValueError("insufficient anchor precision")
    factors = event_factors([r for r in report["applied_events"] if r["code"] == code],
                            number=Fraction)
    raw_anchor = Fraction(positive(history[day][code]))
    multiplier = Fraction(1)
    missing, mismatches, witnesses = [], [], []
    for date in reversed(window):
        raw = Fraction(positive(history[date][code]))
        ratio = raw * multiplier / raw_anchor
        if code not in quotes.get(date, {}):
            missing.append(date)
        else:
            value = Fraction(positive(quotes[date][code]))
            if not (value - half <= ratio * (anchor + half)
                    and ratio * (anchor - half) <= value + half):
                mismatches.append(date)
            if date < day and value <= anchor:
                witnesses.append(date)
        multiplier *= factors.get((code, date), 1)
    low = False if witnesses else (None if missing else True)
    return {"code": code, "date": day, "provider": baseline["provider"],
            "source_url": baseline["source_url"], "display_step": str(display_step),
            "lookback": report["lookback"], "observations": len(window) - len(missing),
            "missing_dates": sorted(missing), "price_ratio_mismatch_dates": sorted(mismatches),
            "external_low_on_displayed_prices": low,
            "most_recent_prior_close_at_or_below_current": max(witnesses, default=None),
            "local_adjusted_low": code in session["adjusted_low_codes"],
            "market_baseline_verified": False, "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "action_report", "baseline"):
        parser.add_argument(name, type=Path)
    parser.add_argument("code")
    parser.add_argument("day")
    parser.add_argument("--display-step", required=True)
    args = parser.parse_args()
    print(json.dumps(check_window(*(json.loads(path.read_text()) for path in
                                   (args.history, args.action_report, args.baseline)),
                                  args.code, args.day, args.display_step), indent=2))
