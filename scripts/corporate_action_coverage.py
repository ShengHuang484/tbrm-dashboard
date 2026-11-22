"""Audit coverage of candidate TWSE corporate-action records.

This does NOT assert that the official endpoint returned every historical event.
No score eligibility is granted by this module.
"""
from datetime import date


def coverage_audit(events, start_date, end_date, requested_months, successful_months):
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError("invalid date range")
    requested = set(requested_months)
    successful = set(successful_months)
    if not successful.issubset(requested):
        raise ValueError("unexpected month")
    bad = []
    observed = set()
    for event in events:
        d = date.fromisoformat(event["ex_date"])
        if not start <= d <= end:
            bad.append(event["ex_date"])
        observed.add(d.strftime("%Y-%m"))
    missing = sorted(requested - successful)
    return {
        "requested_months": sorted(requested),
        "successful_months": sorted(successful),
        "missing_months": missing,
        "events": len(events),
        "event_months": sorted(observed),
        "outside_window_events": bad,
        "request_coverage_complete": not missing and not bad,
        "corporate_action_completeness_verified": False,
        "score_eligible": False,
        "blocking_reasons": [
            "Successful requests do not prove historical event completeness",
            "Capital reductions and other price-basis events require separate official evidence",
            "Daily eligible-stock universe and price basis must be reconciled",
        ],
    }
