"""Consolidated research readiness gate; never authorizes live scoring.

All evidence must be independently approved before the final five points
can be considered. A passing data-structure test is not event verification.
"""
import json
from pathlib import Path


def evaluate(evidence):
    price = evidence["price_reconciliation"]
    universe = evidence["raw_universe_audit"]
    queue = evidence["effective_date_review_queue"]
    identity = evidence["identity_audit"]
    precision = price["price_precision_audit"]
    issues = []
    if not identity.get("identity_audit_passed"):
        issues.append("event_identity_conflicts")
    if precision["exact_price_matches"] != price["matched"]:
        issues.append("nonexact_official_prior_closes")
    if queue["exception_count"]:
        issues.append("unresolved_event_effective_dates")
    if not universe["raw_history_structurally_valid"]:
        issues.append("raw_history_structure_invalid")
    if universe["latest_codes_with_252_consecutive_prior_trading_closes"] < universe["latest_day_codes"]:
        issues.append("incomplete_252_prior_day_stock_coverage")
    if universe["internal_gap_code_count"]:
        issues.append("unclassified_internal_missing_quotes")
    # These are independent evidence requirements, not values inferred from
    # the TWSE ex-rights feed or the raw-close history.
    issues.extend([
        "independent_effective_date_confirmation_missing",
        "capital_reduction_split_merger_event_completeness_unverified",
        "corporate_action_adjustment_factors_unverified",
        "historical_listed_stock_universe_unverified",
        "adjusted_new_low_counts_and_baseline_not_validated",
    ])
    return {
        "research_only": True,
        "candidate_events": price["candidate_count"],
        "exact_official_prior_close_matches": precision["exact_price_matches"],
        "unresolved_event_dates": queue["exception_count"],
        "latest_day_stock_count": universe["latest_day_codes"],
        "strict_252_prior_day_eligible_stocks": universe["latest_codes_with_252_consecutive_prior_trading_closes"],
        "stocks_excluded_by_strict_252_day_rule": universe["latest_day_codes"] - universe["latest_codes_with_252_consecutive_prior_trading_closes"],
        "internal_gap_stock_count": universe["internal_gap_code_count"],
        "blocking_reasons": issues,
        "score_eligible": False,
        "live_points_enabled": 45,
        "live_points_total": 50,
        "next_evidence_needed": {
            "effective_dates": "Independent official trading-day-effective dates for unresolved events",
            "other_actions": "Official capital reduction, split, consolidation and merger coverage",
            "quotes": "Official quote or suspension cross-check for each internal gap",
            "validation": "Verified adjustment factors, adjusted 52-week low counts, and independent baseline comparison",
        },
    }


def build(root):
    required = ("price_reconciliation", "raw_universe_audit",
                "effective_date_review_queue", "identity_audit")
    data = {}
    for name in required:
        path = root / (name + ".json")
        if not path.is_file():
            raise ValueError("missing evidence: " + name)
        data[name] = json.loads(path.read_text(encoding="utf-8"))
    return evaluate(data)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("evidence_dir", type=Path)
    args = p.parse_args()
    report = build(args.evidence_dir)
    (args.evidence_dir / "readiness_decision.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
