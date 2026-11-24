"""Conservative price normalization for verified corporate actions, research only.

Never infer events from daily price jumps. This does not certify event completeness
and must not be used to turn on scoring without a separate universe audit.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


def positive(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid price") from exc
    if not n.is_finite() or n <= 0:
        raise ValueError("invalid price")
    return n


def event_factors(events, *, number=Decimal):
    factors = {}
    for e in events:
        if e.get("verified") is not True:
            raise ValueError("unverified event")
        code = str(e.get("code", ""))
        if len(code) != 4 or not code.isdigit() or code[0] == "0":
            raise ValueError("invalid code")
        day = str(e.get("ex_date", ""))
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("invalid date")
        except ValueError as exc:
            raise ValueError("invalid date") from exc
        if not str(e.get("source_url", "")).startswith("https://"):
            raise ValueError("source URL required")
        if not e.get("event_type"):
            raise ValueError("event type required")
        key = (code, day)
        if key in factors:
            raise ValueError("duplicate event date")
        factors[key] = number(positive(e.get("reference_price"))) / number(positive(e.get("prior_close")))
    return factors


def backward_adjusted_series(dates, closes, events):
    """Apply verified event factors to earlier prices only.

    Dates must be unique ascending; closes maps code to aligned price lists.
    Does not fill missing quotes or establish completeness of corporate actions.
    """
    if dates != sorted(set(dates)):
        raise ValueError("dates must be unique ascending")
    factors = event_factors(events)
    if any(day not in dates for _, day in factors):
        raise ValueError("event outside date window")
    if any(code not in closes for code, _ in factors):
        raise ValueError("verified event has no matching stock price series")
    result = {}
    for code, prices in closes.items():
        if len(prices) != len(dates):
            raise ValueError("incomplete series")
        adjusted = [positive(p) for p in prices]
        multiplier = Decimal("1")
        for i in range(len(dates) - 1, -1, -1):
            adjusted[i] *= multiplier
            if (code, dates[i]) in factors:
                multiplier *= factors[(code, dates[i])]
        result[code] = adjusted
    return result
