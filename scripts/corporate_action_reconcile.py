"""Reconcile candidate ex-right/ex-dividend events with observed daily closes.

An event is *not* certified merely because the exchange supplied a reference
price. Historical close, calendar coverage, and non-TWT49U corporate actions
need independent verification. No score-eligible result is emitted.
"""
from datetime import date
from bisect import bisect_left
from decimal import Decimal, InvalidOperation


def _price(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid close") from exc
    if not n.is_finite() or n <= 0:
        raise ValueError("invalid close")
    return n


def reconcile_candidates(events, history, trading_dates, tolerance="0.011"):
    """Match official pre-event close against immediately prior trading close.

    history: date -> {stock_code: close}. This is a diagnostic only.
    tolerance: maximum relative deviation, defaults to 1.1% to allow a
    conservative rounding screen; it is NOT an approval threshold for scoring.
    """
    if trading_dates != sorted(set(trading_dates)):
        raise ValueError("trading dates must be unique and sorted")
    max_difference = Decimal(str(tolerance))
    if max_difference < 0 or max_difference >= 1:
        raise ValueError("invalid tolerance")
    index = {d: i for i, d in enumerate(trading_dates)}
    checks = []
    for event in events:
        day, code = event["ex_date"], event["code"]
        position = bisect_left(trading_dates, day)
        if position == 0:
            checks.append({"code": code, "ex_date": day, "status": "no_prior_trading_day"})
            continue
        if day not in index:
            checks.append({"code": code, "ex_date": day,
                           "status": "event_date_not_in_history",
                           "preceding_available_date": trading_dates[position - 1]})
            continue
        previous = trading_dates[position - 1]
        observed = history.get(previous, {}).get(code)
        if observed is None:
            checks.append({"code": code, "ex_date": day, "status": "missing_prior_close"})
            continue
        official = _price(event["prior_close"])
        actual = _price(observed)
        deviation = abs(actual / official - 1)
        checks.append({
            "code": code, "ex_date": day, "prior_date": previous,
            "status": "matched_price_basis" if deviation <= max_difference else "price_basis_mismatch",
            "relative_difference": str(deviation),
        })
    return {
        "checks": checks,
        "event_date_not_in_history": sum(c["status"] == "event_date_not_in_history" for c in checks),
        "matched": sum(c["status"] == "matched_price_basis" for c in checks),
        "unresolved": sum(c["status"] != "matched_price_basis" for c in checks),
        "corporate_action_completeness_verified": False,
        "score_eligible": False,
    }
