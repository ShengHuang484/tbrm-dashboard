"""Report merger and exchange evidence without inventing adjustment factors."""
import argparse
import json
from datetime import date
from pathlib import Path

from scripts.corporate_action_audit import positive

KINDS = {
    "listed_survivor_treasury_share_cancellation": "no_holder_exchange_documented",
    "subsidiary_merger_announcement": "exchange_applies_to_subsidiary",
    "listed_share_exchange": "cross_security_exchange",
}


def audit_identity_evidence(history, records):
    dates = sorted(history)
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
        if KINDS.get(event["kind"]) != event["price_basis_status"]:
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
        if event["kind"] == "listed_share_exchange":
            successor = event["successor"]
            if successor == code:
                raise ValueError("cross-security exchange needs two distinct codes")
            positive(event["new_shares_per_old_share"])
            result["predecessor_boundary_conflict"] = bool(subsequent) or not predecessor
            result["successor_already_quoted"] = any(
                session < day and successor in history[session] for session in dates)
        results.append(result)
    return {"records": results, "corporate_action_completeness_verified": False,
            "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    result = audit_identity_evidence(json.loads(args.history.read_text()),
                                     json.loads(args.evidence.read_text()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
