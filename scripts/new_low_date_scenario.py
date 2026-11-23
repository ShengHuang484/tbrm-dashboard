"""Measure the isolated impact of the reconciled ex-right date cases."""
import argparse
import json
from pathlib import Path

from scripts.new_low_adjusted_audit import audit_adjusted_lows


def audit_date_scenario(history, evidence):
    cases = evidence["cases"]
    if not cases or any(row.get("official_trading_basis_matches") is not True for row in cases):
        raise ValueError("every scenario event needs reconciled trading-basis evidence")
    events = [
        {
            "code": row["code"],
            "ex_date": row["candidate_date"],
            "prior_close": row["prior_close"],
            "reference_price": row["reference"],
            "source_url": row["original_report"],
            "event_type": "date_reconciled_ex_right",
            # This assertion permits an isolated research calculation.
            "verified": True,
        }
        for row in cases
    ]
    report = audit_adjusted_lows(history, events)
    report["scenario"] = "reconciled_date_cases_only"
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    result = audit_date_scenario(json.loads(args.history.read_text()),
                                 json.loads(args.evidence.read_text()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
