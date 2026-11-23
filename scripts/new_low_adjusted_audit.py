"""Calculate strict-window low counts for research, even with partial action evidence."""
import argparse
import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from scripts.corporate_action_audit import event_factors, positive


def audit_adjusted_lows(history, events, lookback=252):
    """Use only the current and immediately prior market sessions in history.

    The calendar and listing universe must be corroborated separately. Codes
    with any absent quote in the window are excluded. Present invalid prices
    fail the audit. Factors multiply closes strictly before the effective date;
    later events cannot change an earlier result.
    """
    dates = sorted(history)
    if not 1 <= lookback < len(dates):
        raise ValueError("insufficient market sessions")
    events = list(events)
    factors = event_factors(events, number=Fraction)
    prices = {
        day: {code: positive(close) for code, close in history[day].items()}
        for day in dates
    }
    sessions = {day: index for index, day in enumerate(dates)}
    prior_closes = {(event["code"], event["ex_date"]): positive(event["prior_close"])
                    for event in events}
    action_codes = defaultdict(set)
    for (code, day), factor in factors.items():
        if day not in sessions or code not in prices[day]:
            raise ValueError("verified event has no current-session close")
        for prior_day in reversed(dates[:sessions[day]]):
            if code in prices[prior_day]:
                if prices[prior_day][code] != prior_closes[code, day]:
                    raise ValueError("verified event prior close differs from raw history")
                break
        else:
            raise ValueError("verified event has no raw prior close")
        if factor != 1:
            action_codes[code].add(day)

    results = []
    for index in range(lookback, len(dates)):
        day = dates[index]
        window = dates[index - lookback:index]
        eligible = prices[day].keys() & set.intersection(
            *(set(prices[prior]) for prior in window)
        )
        raw_lows, adjusted_lows = set(), set()
        for code in eligible:
            current = prices[day][code]
            prior_prices = [prices[prior][code] for prior in window]
            raw_low = current < min(prior_prices)
            if raw_low:
                raw_lows.add(code)

            if not any(window[0] < action <= day for action in action_codes.get(code, ())):
                if raw_low:
                    adjusted_lows.add(code)
                continue

            # Only multiply when the event is crossed walking backwards.
            multiplier = Fraction(1)
            for position in range(lookback - 1, -1, -1):
                next_day = day if position == lookback - 1 else window[position + 1]
                multiplier *= factors.get((code, next_day), 1)
                if Fraction(current) >= Fraction(prior_prices[position]) * multiplier:
                    break
            else:
                adjusted_lows.add(code)

        results.append({
            "date": day,
            "quoted_codes": len(prices[day]),
            "strict_eligible": len(eligible),
            "missing_prior_quote": len(prices[day]) - len(eligible),
            "raw_low_count": len(raw_lows),
            "adjusted_low_count": len(adjusted_lows),
            "added_low_codes": sorted(adjusted_lows - raw_lows),
            "removed_low_codes": sorted(raw_lows - adjusted_lows),
        })
    return {
        "lookback": lookback,
        "factor_count": len(factors),
        "corporate_action_completeness_verified": False,
        "listing_universe_verified": False,
        "research_only": True,
        "score_eligible": False,
        "sessions": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("verified_events", type=Path)
    args = parser.parse_args()
    report = audit_adjusted_lows(
        json.loads(args.history.read_text(encoding="utf-8")),
        json.loads(args.verified_events.read_text(encoding="utf-8")),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
