"""Assemble corroborated research factors and screen for omissions."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.monthly_ex_right_scenario import load_months, reconcile_months


def assemble(history, ex_right, crosscheck, face_actions, reduction_boundary):
    first = min(history)
    latest = {}
    previous_at_event = {}
    keys = {(r["code"], r["candidate_date"]) for r in ex_right["cases"]}
    keys.update((r["code"], r["date"]) for r in crosscheck["checks"])
    keys.update((r["code"], r["effective_date"]) for r in face_actions)
    for day in sorted(history):
        for code, price in history[day].items():
            if (code, day) in keys:
                previous_at_event[code, day] = latest.get(code)
            latest[code] = (day, price)

    events, boundary = [], []

    def add(code, day, prior, reference, source, kind, prior_date=None):
        observed = previous_at_event.get((code, day))
        if code not in history.get(day, {}):
            raise ValueError(f"missing effective-day quote: {code} {day}")
        if observed is None and prior_date and prior_date < first:
            boundary.append({"code": code, "date": day, "prior_date": prior_date,
                             "reason": "no_pre_event_closes_in_archive"})
            return
        if observed is None or positive(observed[1]) != positive(prior):
            raise ValueError(f"pre-event close mismatch: {code} {day}")
        if prior_date and observed[0] != prior_date:
            raise ValueError(f"pre-event date mismatch: {code} {day}")
        events.append({"code": code, "ex_date": day, "prior_close": str(prior),
                       "reference_price": str(reference), "source_url": source,
                       "event_type": kind, "verified": True})

    for row in ex_right["cases"]:
        if row.get("official_trading_basis_matches") is not True:
            raise ValueError("unreconciled ex-right date")
        add(row["code"], row["candidate_date"], row["prior_close"], row["reference"],
            row["original_report"], "reconciled_ex_right", row["prior_date"])

    for row in crosscheck["checks"]:
        if not (row["prior_close_matches"] and row["resumption_reference_matches"]):
            raise ValueError("unreconciled reduction")
        peer = row["secondary"]
        if (peer["stock_id"], peer["date"]) != (row["code"], row["date"]):
            raise ValueError("reduction identity mismatch")
        if (positive(peer["ClosingPriceonTheLastTradingDay"]) != positive(row["twse_pre_halt_close"])
                or positive(peer["PostReductionReferencePrice"]) != positive(row["twse_resumption_reference"])):
            raise ValueError("reduction price mismatch")
        if Decimal(str(peer["ExrightReferencePrice"])) != -1:
            raise ValueError("reduction has a separate rights reference requiring review")
        prior_date = None
        if row["code"] == reduction_boundary["code"] and positive(
                reduction_boundary["close"]) == positive(row["twse_pre_halt_close"]):
            prior_date = reduction_boundary["date"]
        add(row["code"], row["date"], row["twse_pre_halt_close"],
            row["twse_resumption_reference"], crosscheck["primary_archive"],
            "capital_reduction", prior_date)

    for row in face_actions:
        code, day = row["code"], row["effective_date"]
        peers = [p for p in crosscheck["par_value_changes"] if
                 (p["stock_id"], p["date"]) == (code, day)]
        if len(peers) != 1:
            raise ValueError(f"missing or ambiguous face-value corroboration: {code}")
        peer = peers[0]
        numerator = positive(row["new_face_value"])
        denominator = positive(row["old_face_value"])
        reference = positive(peer["before_close"]) * numerator / denominator
        if reference != positive(peer["after_ref_close"]):
            raise ValueError(f"face-value reference mismatch: {code}")
        add(code, day, peer["before_close"], reference, row["issuer_url"],
            "split" if numerator < denominator else "reverse_split", row["prior_date"])

    event_keys = [(event["code"], event["ex_date"]) for event in events]
    if len(set(event_keys)) != len(event_keys):
        raise ValueError("overlapping corporate actions require a combined reference")
    return events, boundary


def screen_discontinuities(history, events, boundary, threshold="0.30", max_gap=10):
    """Find large close discontinuities as leads, with no inferred factors."""
    threshold = positive(threshold)
    covered = {(e["code"], e["ex_date"]) for e in events}
    covered.update((entry["code"], entry["date"]) for entry in boundary)
    previous = {}
    candidates = []
    for index, day in enumerate(sorted(history)):
        for code, close in history[day].items():
            price = positive(close)
            old = previous.get(code)
            previous[code] = (index, day, price)
            if old is None or (code, day) in covered:
                continue
            old_index, old_day, old_price = old
            gap = index - old_index - 1
            if gap <= max_gap and abs(price / old_price - 1) >= threshold:
                candidates.append({
                    "code": code, "date": day, "prior_date": old_day, "gap_sessions": gap,
                    "prior_close": str(old_price), "close": str(price),
                    "relative_change": str(price / old_price - 1),
                })
    return candidates


def classify_latest_lookback_gaps(history, events, lookback):
    """Attribute missing quote intervals without imputing or certifying a halt."""
    days = sorted(history)
    if not 1 <= lookback < len(days):
        raise ValueError("insufficient sessions for gap audit")
    positions = {day: index for index, day in enumerate(days)}
    action_types = {"capital_reduction", "split", "reverse_split"}
    bounded = set()
    for event in events:
        if event["event_type"] not in action_types:
            continue
        code = event["code"]
        stop = positions[event["ex_date"]]
        prior = next((i for i in range(stop - 1, -1, -1) if code in history[days[i]]), None)
        if prior is not None:
            bounded.update((code, day) for day in days[prior + 1:stop])

    scope = days[-lookback - 1:-1]
    bounded_count, other_count = 0, 0
    affected, unexplained = set(), set()
    for code in history[days[-1]]:
        for day in scope:
            if code in history[day]:
                continue
            if (code, day) in bounded:
                bounded_count += 1
                affected.add(code)
            else:
                other_count += 1
                unexplained.add(code)
    return {
        "date": days[-1],
        "action_bounded_missing_pairs": bounded_count,
        "other_missing_pairs": other_count,
        "codes_with_action_bounded_gaps": len(affected),
        "codes_with_other_gaps": len(unexplained),
        "codes_missing_prior_quotes": len(affected | unexplained),
        "verified_halt_dates": False,
    }


def audit(history, ex_right, crosscheck, face_actions, reduction_boundary, *, monthly_archives=()):
    events, boundary = assemble(history, ex_right, crosscheck, face_actions, reduction_boundary)
    excluded, hashes = [], {}
    if monthly_archives:
        records, hashes = load_months(monthly_archives, sorted(history))
        monthly_events, excluded = reconcile_months(history, records, ex_right, events)
        events.extend(monthly_events)
    result = audit_adjusted_lows(history, events)
    result.update({
        "scenario": "monthly_archive_reconciliation" if hashes else "corroborated_subset",
        "monthly_hashes": hashes,
        "monthly_exclusions": excluded,
        "applied_events": events,
        "boundary_events": boundary,
        "latest_lookback_gaps": classify_latest_lookback_gaps(history, events, result["lookback"]),
        "unexplained_discontinuities": screen_discontinuities(history, events, boundary),
    })
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("--evidence-directory", type=Path, default=Path("research"))
    parser.add_argument("--monthly-archives", nargs="+", type=Path, default=[])
    args = parser.parse_args()
    root = args.evidence_directory
    evidence = [json.loads((root / name).read_text(encoding="utf-8")) for name in (
        "ex_right_date_results.json", "finmind_action_crosscheck.json", "face_value_issuers.json",
        "lifecycle_crosscheck_results.json",
    )]
    evidence[-1] = evidence[-1]["reduction_pre_window_close"]
    result = audit(json.loads(args.history.read_text(encoding="utf-8")), *evidence,
                   monthly_archives=args.monthly_archives)
    print(json.dumps(result, ensure_ascii=False, indent=2))
