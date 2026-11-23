"""Check the structure and market coverage of a supplier delivery for human review."""
import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.new_low_baseline import compare
from scripts.new_low_baseline_import import normalize
from scripts.new_low_listing import listing_windows, listings_on
from scripts.new_low_rights_scenario import TWSE_REFERENCE, ZERO_RIGHTS

RULES = ("cash_dividend", "stock_dividend", "rights_issue", "capital_reduction",
         "split", "reverse_split", "merger")


def inspect(report, metadata, quotes, calendar, listings):
    if metadata.get("currency") != "TWD" or metadata.get("timezone") != "Asia/Taipei":
        raise ValueError("delivery must declare TWD and Asia/Taipei")
    exported = metadata.get("exported_on", "")
    if date.fromisoformat(exported).isoformat() != exported or exported < report["market_dates"][-1]:
        raise ValueError("invalid delivery export date")
    basis = metadata.get("rights_basis")
    if basis not in (TWSE_REFERENCE, ZERO_RIGHTS) or basis != report.get("rights_basis"):
        raise ValueError("delivery rights basis differs from selected research basis")
    digits = metadata.get("price_decimal_places")
    if type(digits) is not int or digits < 0:
        raise ValueError("missing price decimal precision")
    rules = metadata.get("corporate_action_rules", {})
    if any(not isinstance(rules.get(key), str) or not rules[key].strip() for key in RULES):
        raise ValueError("delivery must document all corporate action rules")

    baseline = normalize(metadata, quotes, calendar, listings)
    for day, prices in baseline["adjusted_closes"].items():
        for code, raw in prices.items():
            digits_in_value = -Decimal(raw).as_tuple().exponent
            if digits_in_value > digits:
                raise ValueError(f"quote precision exceeds delivery declaration: {day} {code}")
    comparison = compare(report, baseline)
    local = listing_windows(report["listing_intervals"])
    external = listing_windows(baseline["listings"])
    coverage = []
    for day in baseline["market_dates"]:
        local_active = listings_on(local, day)
        vendor_active = listings_on(external, day)
        local_only = sorted(local_active.keys() - vendor_active.keys())
        vendor_only = sorted(vendor_active.keys() - local_active.keys())
        changed_start = sorted(code for code in local_active.keys() & vendor_active.keys()
                               if local_active[code][0] != vendor_active[code][0])
        if local_only or vendor_only or changed_start:
            coverage.append(dict(date=day, local_only=local_only, vendor_only=vendor_only,
                                 differing_listing_start=changed_start))
    for row in comparison["sessions"]:
        reasons = {}
        for field, label in (
            ("external_only_eligible_codes", "external_eligible_only"),
            ("local_only_eligible_codes", "local_eligible_only"),
            ("external_only_low_codes", "external_low_only"),
            ("local_only_low_codes", "local_low_only"),
        ):
            for code in row[field]:
                reasons.setdefault(code, []).append(label)
        row["disagreement_by_code"] = reasons
    return dict(delivery_metadata=metadata, listing_disagreement=coverage,
                comparison=comparison, score_eligible=False, market_baseline_verified=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("report", "metadata", "quotes", "calendar", "listings"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(json.loads(args.report.read_text()), json.loads(args.metadata.read_text()),
                             *(p.read_bytes() for p in (args.quotes, args.calendar, args.listings))),
                     ensure_ascii=False, indent=2))
