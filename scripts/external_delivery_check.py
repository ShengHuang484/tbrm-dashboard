"""Check the structure and market coverage of a supplier delivery for human review."""
import argparse
import hashlib
import json
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.corporate_action_external_validation import compare_transition, ratio_interval
from scripts.new_low_baseline import compare
from scripts.new_low_baseline_import import normalize
from scripts.new_low_listing import listing_windows, listings_on
from scripts.new_low_rights_scenario import TWSE_REFERENCE, ZERO_RIGHTS

RULES = ("cash_dividend", "stock_dividend", "rights_issue", "capital_reduction",
         "split", "reverse_split", "merger")


def price_movement_differences(history, report, baseline, local, external, digits):
    dates = baseline["market_dates"]
    if sorted(history) != dates:
        raise ValueError("raw history does not match delivery calendar")
    events = {(e["code"], e["ex_date"]): e for e in report.get("applied_events", [])}
    prices = baseline["adjusted_closes"]
    half_step = Fraction(1, 2 * 10 ** digits)
    prior = dates[0]
    previous_vendor = listings_on(external, prior)
    previous_local = listings_on(local, prior)
    results = []
    for day in dates[1:]:
        vendor = listings_on(external, day)
        local_listed = listings_on(local, day)
        comparable = history[prior].keys() & history[day].keys() & prices[prior].keys() & prices[day].keys()
        tested = 0
        differences = {}
        boundaries = []
        for code in sorted(comparable):
            if code not in vendor or code not in local_listed:
                continue
            if vendor[code] != previous_vendor.get(code) or local_listed[code] != previous_local.get(code):
                boundaries.append(code)
                continue
            left, right = (Fraction(positive(prices[d][code])) for d in (prior, day))
            event = events.get((code, day))
            reference = event["reference_price"] if event else history[prior][code]
            expected = Fraction(positive(history[day][code])) / Fraction(positive(reference))
            if min(left, right) <= half_step:
                differences[code] = {"status": "insufficient_price_precision"}
                continue
            lower, upper = ratio_interval(left, right, half_step)
            tested += 1
            if not lower <= expected <= upper:
                differences[code] = dict(status="price_movement_difference",
                    expected_ratio=str(expected), vendor_interval=[str(lower), str(upper)],
                    event_reference=event is not None)
        results.append(dict(date=day, prior_date=prior, compared=tested,
                            differences_by_code=differences, listing_boundaries=boundaries))
        prior, previous_vendor, previous_local = day, vendor, local_listed
    return results


def check_event_samples(history, report, baseline, cases, digits):
    events = {(r["code"], r["ex_date"]): r for r in report["applied_events"]}
    results = []
    for case in cases:
        kind = case["action"]
        code, before, after = (case[k] for k in ("code", "before_date", "effective_date"))
        if kind not in RULES or not case["evidence_url"].startswith("https://"):
            raise ValueError("event comparison requires documented event semantics")
        event = events.get((code, after))
        if event is None:
            raise ValueError(f"no reference-price event for {code} on {after}")
        prices = baseline["adjusted_closes"]
        left, right = (prices.get(day, {}).get(code) for day in (before, after))
        row = dict(action=kind, code=code, effective_date=after,
                   evidence_url=case["evidence_url"])
        if None in (left, right):
            results.append(dict(row, status="missing_vendor_transition_quote"))
            continue
        sample = dict(case, source_url=baseline["source_url"], external_before=left,
                      external_after=right, reference=event["reference_price"],
                      display_step=str(Decimal(1).scaleb(-digits)))
        checked = compare_transition(history, sample)
        status = "within_display_precision" if checked["agrees_with_display_precision"] else "price_basis_difference"
        results.append(dict(row, status=status, comparison=checked))
    return results


def inspect(report, metadata, quotes, calendar, listings, *,
            alternative=None, history=None, event_cases=()):
    if metadata.get("currency") != "TWD" or metadata.get("timezone") != "Asia/Taipei":
        raise ValueError("delivery must declare TWD and Asia/Taipei")
    exported = metadata.get("exported_on", "")
    if date.fromisoformat(exported).isoformat() != exported or exported < report["market_dates"][-1]:
        raise ValueError("invalid delivery export date")
    basis = metadata.get("rights_basis")
    if basis not in (TWSE_REFERENCE, ZERO_RIGHTS) or basis != report.get("rights_basis"):
        raise ValueError("delivery rights basis differs from selected research basis")
    digits = metadata.get("price_decimal_places")
    if type(digits) is not int or not 0 <= digits <= 30:
        raise ValueError("missing price decimal precision")
    rules = metadata.get("corporate_action_rules", {})
    if any(not isinstance(rules.get(key), str) or not rules[key].strip() for key in RULES):
        raise ValueError("delivery must document all corporate action rules")

    baseline = normalize(metadata, quotes, calendar, listings, expected_dates=report["market_dates"])
    for day, prices in baseline["adjusted_closes"].items():
        for code, raw in prices.items():
            digits_in_value = -Decimal(raw).as_tuple().exponent
            if digits_in_value > digits:
                raise ValueError(f"quote precision exceeds delivery declaration: {day} {code}")
    comparison = compare(report, baseline)
    alternatives = {}
    if alternative is not None:
        other_basis = ZERO_RIGHTS if basis == TWSE_REFERENCE else TWSE_REFERENCE
        if (alternative.get("rights_basis") != other_basis
                or alternative["lookback"] != report["lookback"]
                or alternative["listing_intervals"] != report["listing_intervals"]):
            raise ValueError("alternative must use the other rights basis and identical listing scope")
        for a, b in zip(report["sessions"], alternative["sessions"], strict=True):
            if (a["date"] != b["date"] or set(a["eligible_codes"]) != set(b["eligible_codes"])
                    or (set(a["adjusted_low_codes"]) ^ set(b["adjusted_low_codes"])) - {"1312"}):
                raise ValueError("alternative changes more than the documented 1312 decision")
        alternatives = compare(alternative, baseline)
    if event_cases and history is None:
        raise ValueError("event samples require archived raw closes")
    price_checks = check_event_samples(history, report, baseline, event_cases, digits) if event_cases else []
    alternative_price_checks = (
        check_event_samples(history, alternative, baseline, event_cases, digits)
        if event_cases and alternative is not None else [])
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
    identities = {}
    security_codes = {}
    for row in baseline["listings"]:
        identities.setdefault(row["code"], []).append(row)
        if "security_id" in row:
            security_codes.setdefault(row["security_id"], []).append(row)
    reused_codes = {code: sorted(intervals, key=lambda r: r["listed_from"])
                    for code, intervals in identities.items() if len(intervals) > 1}
    code_transitions = {security: sorted(intervals, key=lambda r: r["listed_from"])
                        for security, intervals in security_codes.items()
                        if len({r["code"] for r in intervals}) > 1}
    return dict(delivery_metadata=metadata, listing_disagreement=coverage,
                comparison=comparison, alternative_basis_diagnostic=alternatives,
                vendor_repeated_listing_codes=reused_codes,
                vendor_security_code_transitions=code_transitions,
                price_movement_checks=price_movement_differences(history, report, baseline, local, external, digits)
                if history is not None else [],
                alternative_price_movement_checks=price_movement_differences(
                    history, alternative, baseline, local, external, digits)
                if history is not None and alternative is not None else [],
                event_price_checks=price_checks, alternative_event_price_checks=alternative_price_checks,
                event_types_without_sample=sorted(set(RULES) - {r["action"] for r in price_checks
                    if r["status"] != "missing_vendor_transition_quote"}),
                score_eligible=False, market_baseline_verified=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("report", "metadata", "quotes", "calendar", "listings"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--alternative-report", type=Path)
    parser.add_argument("--raw-history", type=Path)
    parser.add_argument("--event-cases", type=Path)
    args = parser.parse_args()
    def read(path):
        return json.loads(path.read_text()) if path else None
    metadata = args.metadata.read_bytes()
    result = inspect(read(args.report), json.loads(metadata),
                     *(p.read_bytes() for p in (args.quotes, args.calendar, args.listings)),
                     alternative=read(args.alternative_report), history=read(args.raw_history),
                     event_cases=read(args.event_cases) or [])
    result["source_metadata_sha256"] = hashlib.sha256(metadata).hexdigest()
    print(json.dumps(result, ensure_ascii=False, indent=2))
