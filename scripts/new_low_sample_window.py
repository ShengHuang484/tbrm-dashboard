"""Audit one eligible stock against provider closes over the actual research window."""
import argparse
import json
from datetime import date as iso_date
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
    strictly_lower, ambiguous = [], []
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
            if date < day:
                if value + half < anchor - half:
                    strictly_lower.append(date)
                elif value - half <= anchor + half:
                    ambiguous.append(date)
        multiplier *= factors.get((code, date), 1)
    low = False if witnesses else (None if missing else True)
    return {"code": code, "date": day, "provider": baseline["provider"],
            "source_url": baseline["source_url"], "display_step": str(display_step),
            "lookback": report["lookback"], "observations": len(window) - len(missing),
            "missing_dates": sorted(missing), "price_ratio_mismatch_dates": sorted(mismatches),
            "external_low_on_displayed_prices": low,
            "most_recent_prior_close_at_or_below_current": max(witnesses, default=None),
            "external_low_beyond_display_rounding": (
                False if strictly_lower else None if missing or ambiguous else True),
            "strictly_lower_prior_dates": sorted(strictly_lower),
            "rounding_ambiguous_prior_dates": sorted(ambiguous),
            "local_adjusted_low": code in session["adjusted_low_codes"],
            "market_baseline_verified": False, "score_eligible": False}


def weekly_baseline(dates, code, evidence):
    """Map a provider weekly close only to its documented last market session."""
    if not evidence["source_url"].startswith("https://"):
        raise ValueError("weekly evidence requires a source")
    adjusted = {}
    week_ends = {}
    for day in dates:
        year, week, _ = iso_date.fromisoformat(day).isocalendar()
        week_ends[year, week] = day
    for row in evidence["weekly_closes"]:
        day = row["last_session"]
        year, week, weekday = iso_date.fromisoformat(day).isocalendar()
        if (week_ends.get((year, week)) != day or day in adjusted
                or (day == dates[-1] and weekday < 5)):
            raise ValueError("weekly close must identify a unique completed market week")
        adjusted[day] = {code: str(positive(row["adjusted_close"]))}
    return dict(provider=evidence["provider"], source_url=evidence["source_url"],
                market_dates=dates, adjusted_closes=adjusted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "action_report", "baseline"):
        parser.add_argument(name, type=Path)
    parser.add_argument("code")
    parser.add_argument("day")
    parser.add_argument("--display-step", required=True)
    parser.add_argument("--weekly", action="store_true")
    args = parser.parse_args()
    history, report, baseline = (json.loads(path.read_text()) for path in
                                 (args.history, args.action_report, args.baseline))
    if args.weekly:
        baseline = weekly_baseline(report["market_dates"], args.code, baseline)
    print(json.dumps(check_window(history, report, baseline, args.code, args.day,
                                  args.display_step), indent=2))
