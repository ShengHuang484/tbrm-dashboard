"""Sensitivity of a provider window to unrounded issuer cash distributions."""
import argparse
import json
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.new_low_sample_window import check_window


def compare_cash_basis(history, report, baseline, evidence, day, step):
    code = evidence["code"]
    if not evidence["source_url"].startswith("https://"):
        raise ValueError("issuer source required")
    payments = {r["ex_date"]: positive(r["cash_per_common_share_twd"])
                for r in evidence["cash_only_distributions"]}
    if len(payments) != len(evidence["cash_only_distributions"]):
        raise ValueError("duplicate issuer cash evidence")
    replacements = []
    events = []
    for event in report["applied_events"]:
        event_day = event["ex_date"]
        if event["code"] == code and event_day in payments:
            if event["event_type"] != "monthly_ex_right_reconciled":
                raise ValueError("expected a corroborated ex-dividend event")
            reference = positive(event["prior_close"]) - payments.pop(event_day)
            positive(reference)
            replacements.append(dict(ex_date=event_day, official_reference=event["reference_price"],
                                     issuer_cash_reference=str(reference)))
            event = dict(event, reference_price=str(reference))
        events.append(event)
    if payments:
        raise ValueError("issuer event missing from reconciled research factors")
    original = check_window(history, report, baseline, code, day, step)
    scenario = check_window(history, dict(report, applied_events=events), baseline, code, day, step)
    return {"code": code, "date": day, "issuer_source": evidence["source_url"],
            "provider_source": baseline["source_url"], "references": replacements,
            "compared_observations": scenario["observations"],
            "official_basis_mismatch_dates": original["price_ratio_mismatch_dates"],
            "issuer_cash_basis_mismatch_dates": scenario["price_ratio_mismatch_dates"],
            "missing_observations": len(scenario["missing_dates"]),
            "market_baseline_verified": False, "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "action_report", "baseline", "issuer_evidence"):
        parser.add_argument(name, type=Path)
    parser.add_argument("day")
    parser.add_argument("--display-step", required=True)
    args = parser.parse_args()
    print(json.dumps(compare_cash_basis(*(json.loads(p.read_text()) for p in
                     (args.history, args.action_report, args.baseline, args.issuer_evidence)),
                     args.day, args.display_step), indent=2))
