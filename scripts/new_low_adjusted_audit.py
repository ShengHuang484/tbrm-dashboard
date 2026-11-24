"""Calculate strict-window low counts for research, even with partial action evidence."""
import argparse
import json
from bisect import bisect_left
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from scripts.corporate_action_audit import event_factors, positive
from scripts.new_low_listing import listing_windows, listings_on


STRICT_SESSIONS = "strict_market_sessions"
OBSERVED_QUOTES = "prior_observed_quotes"


def audit_adjusted_lows(history, events, lookback=252, *, listings=None, quote_policy=STRICT_SESSIONS):
    """Use a strict market-session window or a sensitivity window of observed quotes.

    The calendar and listing universe must be corroborated separately. Codes
    lacking the required number of prior quotes are excluded. Present invalid prices
    fail the audit. Factors multiply closes strictly before the effective date;
    later events cannot change an earlier result.
    """
    if quote_policy not in (STRICT_SESSIONS, OBSERVED_QUOTES):
        raise ValueError("unknown lookback quote policy")
    observed = quote_policy == OBSERVED_QUOTES
    dates = sorted(history)
    if not 1 <= lookback < len(dates):
        raise ValueError("insufficient market sessions")
    listing_index = None if listings is None else listing_windows(listings)
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
        if listing_index is not None:
            active = listings_on(listing_index, day).get(code)
            if active is None or prior_day < active[0]:
                raise ValueError("event crosses a listing interval")
        if factor != 1:
            action_codes[code].add(day)

    quoted_days = defaultdict(list)
    if observed:
        for day in dates:
            for code in prices[day]:
                quoted_days[code].append(day)
    results = []
    for index in range(lookback, len(dates)):
        day = dates[index]
        window = dates[index - lookback:index]
        stock_windows = {}
        if observed:
            for code in prices[day]:
                observed_dates = quoted_days[code]
                end = bisect_left(observed_dates, day)
                if end >= lookback:
                    stock_windows[code] = observed_dates[end - lookback:end]
            eligible = set(stock_windows)
        else:
            eligible = prices[day].keys() & set.intersection(
                *(set(prices[prior]) for prior in window)
            )
        listing_diagnostics = {}
        if listing_index is not None:
            listed = listings_on(listing_index, day)
            continuous = {code for code, (start, _) in listed.items() if start <= window[0]}
            quoted = prices[day].keys() & continuous
            eligible &= continuous
            if observed:
                eligible = {code for code in eligible if listed[code][0] <= stock_windows[code][0]}
            listing_diagnostics = {
                "active_listings": len(listed),
                "outside_active_listing": len(prices[day].keys() - listed.keys()),
                "insufficient_listing_age": len(listed) - len(continuous),
                "unquoted_current_listings": len(listed.keys() - prices[day].keys()),
                "missing_prior_quote": len(quoted) - len(eligible),
            }
        raw_lows, adjusted_lows = set(), set()
        for code in eligible:
            current = prices[day][code]
            stock_window = stock_windows[code] if observed else window
            prior_prices = [prices[prior][code] for prior in stock_window]
            raw_low = current < min(prior_prices)
            if raw_low:
                raw_lows.add(code)

            if not any(stock_window[0] < action <= day for action in action_codes.get(code, ())):
                if raw_low:
                    adjusted_lows.add(code)
                continue

            # Only multiply when the event is crossed walking backwards.
            multiplier = Fraction(1)
            for position in range(lookback - 1, -1, -1):
                next_day = day if position == lookback - 1 else stock_window[position + 1]
                multiplier *= factors.get((code, next_day), 1)
                if Fraction(current) >= Fraction(prior_prices[position]) * multiplier:
                    break
            else:
                adjusted_lows.add(code)

        results.append({
            "date": day,
            "quoted_codes": len(prices[day]),
            "eligible_count": len(eligible),
            **({} if observed else {"strict_eligible": len(eligible)}),
            "missing_prior_quote": len(prices[day]) - len(eligible),
            "raw_low_count": len(raw_lows),
            "adjusted_low_count": len(adjusted_lows),
            "added_low_codes": sorted(adjusted_lows - raw_lows),
            "removed_low_codes": sorted(raw_lows - adjusted_lows),
            "eligible_codes": sorted(eligible),
            "adjusted_low_codes": sorted(adjusted_lows),
            **listing_diagnostics,
        })
    return {
        "lookback": lookback,
        "quote_policy": quote_policy,
        "market_dates": dates,
        "factor_count": len(factors),
        "listing_intervals_supplied": listing_index is not None,
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
    parser.add_argument("--listings", type=Path)
    parser.add_argument("--quote-policy", choices=(STRICT_SESSIONS, OBSERVED_QUOTES), default=STRICT_SESSIONS)
    args = parser.parse_args()
    report = audit_adjusted_lows(
        json.loads(args.history.read_text(encoding="utf-8")),
        json.loads(args.verified_events.read_text(encoding="utf-8")),
        listings=json.loads(args.listings.read_text()) if args.listings else None,
        quote_policy=args.quote_policy,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
