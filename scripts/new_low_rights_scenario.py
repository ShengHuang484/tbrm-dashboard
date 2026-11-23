"""Compare an above-market cash subscription event with a zero-rights-value scenario."""
import argparse
import json
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.corporate_action_external_validation import compare_transition
from scripts.new_low_adjusted_audit import audit_adjusted_lows


TWSE_REFERENCE = "twse-reference"
ZERO_RIGHTS = "zero-rights"


def select_events(events, basis=TWSE_REFERENCE, evidence=None):
    if basis == TWSE_REFERENCE:
        return list(events)
    if basis != ZERO_RIGHTS or evidence is None:
        raise ValueError("zero-rights basis requires documented rights evidence")
    key = evidence["code"], evidence["effective_date"]
    matches = [r for r in events if (r["code"], r["ex_date"]) == key]
    if len(matches) != 1 or matches[0]["event_type"] != "monthly_ex_right_reconciled":
        raise ValueError("expected one reconciled monthly event")
    event, = matches
    close = positive(evidence["prior_close"])
    if not (close == positive(event["prior_close"])
            == positive(evidence["dividend_only_reference"])
            == positive(evidence["auction_basis"])
            < positive(event["reference_price"])
            == positive(evidence["official_reference"])
            < positive(evidence["subscription_price"])):
        raise ValueError("prices do not describe a pure above-market subscription")
    replacement = dict(event, reference_price=str(close))
    return [replacement if r is event else r for r in events]


def compare(history, report, evidence):
    key = evidence["code"], evidence["effective_date"]
    events = select_events(report["applied_events"], ZERO_RIGHTS, evidence)
    scenario = audit_adjusted_lows(history, events, report["lookback"])
    changes = []
    for old, new in zip(report["sessions"], scenario["sessions"], strict=True):
        if (old["date"] != new["date"] or old["eligible_codes"] != new["eligible_codes"]):
            raise ValueError("comparison requires the original strict cohort")
        removed = set(old["adjusted_low_codes"]) - set(new["adjusted_low_codes"])
        added = set(new["adjusted_low_codes"]) - set(old["adjusted_low_codes"])
        if removed or added:
            changes.append(dict(date=old["date"], original=old["adjusted_low_count"],
                                scenario=new["adjusted_low_count"],
                                removed=sorted(removed), added=sorted(added)))
    external = evidence.get("external_transition")
    transition = {}
    if external is not None:
        sample = dict(external, code=key[0], effective_date=key[1])
        transition = {
            name: compare_transition(history, dict(sample, reference=reference))
            for name, reference in (("official_reference", evidence["official_reference"]),
                                    ("zero_rights_value", evidence["dividend_only_reference"]))
        }
    return dict(external_transition=transition, code=key[0], effective_date=key[1], sessions=len(scenario["sessions"]),
                changed_sessions=changes, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("history", "report", "evidence"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    documents = [json.loads(p.read_text()) for p in (args.history, args.report, args.evidence)]
    print(json.dumps(compare(*documents), indent=2))
