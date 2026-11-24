"""Report merger and exchange evidence without inventing adjustment factors."""
import argparse
import json
from datetime import date
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.new_low_listing import listing_windows, listings_on

KINDS = {
    "listed_survivor_treasury_share_cancellation": "no_holder_exchange_documented",
    "subsidiary_merger_announcement": "exchange_applies_to_subsidiary",
    "listed_acquirer_issues_exchange_shares": "consideration_to_acquired_company_holders",
    "listed_cash_exchange": "cash_exit",
    "deferred_subsidiary_merger": "pending_effective_date",
    "listed_share_exchange": "cross_security_exchange",
}


def audit_identity_evidence(history, records, listings=None):
    dates = sorted(history)
    windows = listing_windows(listings) if listings is not None else None
    used = set()
    results = []
    for event in records:
        code, day = event["code"], event["reference_date"]
        identity = code, day, event["kind"]
        if identity in used:
            raise ValueError("duplicate identity evidence")
        used.add(identity)
        if date.fromisoformat(day).isoformat() != day or not dates[0] <= day <= dates[-1]:
            raise ValueError("identity evidence outside the review window")
        if event["kind"] not in KINDS or KINDS[event["kind"]] != event["price_basis_status"]:
            raise ValueError("unknown identity action or price-basis status")
        sources = event["sources"]
        if len(set(sources)) < 2 or any(not url.startswith("https://") for url in sources):
            raise ValueError("two traceable sources are required")
        quoted = [session for session in dates if code in history[session]]
        predecessor = [session for session in quoted if session < day]
        subsequent = [session for session in quoted if session >= day]
        result = dict(event, last_pre_reference_quote=predecessor[-1] if predecessor else None,
                      first_at_or_after_reference_quote=subsequent[0] if subsequent else None,
                      factor=None, cross_security_history_splice=False)
        if event["kind"] == "listed_acquirer_issues_exchange_shares":
            if (not event["target_entity"].strip()
                    or any(type(event[field]) is not int or event[field] <= 0
                           for field in ("shares_issued", "target_shares_acquired"))):
                raise ValueError("invalid new-share consideration")
            result["listed_acquirer_quote_boundary_conflict"] = not predecessor or day not in quoted
        if event["kind"] == "deferred_subsidiary_merger":
            if event["effective_date"] is not None:
                raise ValueError("a deferred announcement cannot confirm an effective date")
        if event["kind"] in ("listed_share_exchange", "listed_cash_exchange"):
            successor = event["successor"]
            if successor == code:
                raise ValueError("cross-security exchange needs two distinct codes")
            if event["kind"] == "listed_cash_exchange":
                positive(event["cash_twd_per_old_share"])
                stop = event["trading_stops_on"]
                if date.fromisoformat(stop).isoformat() != stop or stop > day:
                    raise ValueError("invalid stop-trading boundary")
                result["quoted_during_stop"] = [d for d in predecessor if d >= stop]
            else:
                positive(event["new_shares_per_old_share"])
            result["predecessor_boundary_conflict"] = bool(subsequent) or not predecessor
            result["successor_already_quoted"] = any(
                session < day and successor in history[session] for session in dates)
            if windows is not None:
                current = listings_on(windows, day)
                prior_session = max((session for session in dates if session < day), default=None)
                earlier = listings_on(windows, prior_session) if prior_session else {}
                old_interval = earlier.get(code)
                survivor = current.get(successor)
                result["listing_boundary_review"] = {
                    "predecessor_exits_on_reference_date": (
                        old_interval is not None and old_interval[1] == day and code not in current),
                    "successor_active_on_reference_date": survivor is not None,
                    "successor_same_listing_interval": survivor is not None and survivor == earlier.get(successor),
                }
        result["last_pre_reference_close"] = history[predecessor[-1]][code] if predecessor else None
        results.append(result)
    return {"records": results, "corporate_action_completeness_verified": False,
            "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--listing-report", type=Path)
    args = parser.parse_args()
    listings = json.loads(args.listing_report.read_text())["listing_intervals"] if args.listing_report else None
    result = audit_identity_evidence(json.loads(args.history.read_text()),
                                     json.loads(args.evidence.read_text()), listings)
    print(json.dumps(result, ensure_ascii=False, indent=2))
