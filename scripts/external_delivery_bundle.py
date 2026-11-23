"""Run the full research intake checks over a licensed or synthetic delivery."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from scripts.external_delivery_check import RULES, inspect
from scripts.historical_roster_check import check
from scripts.new_low_baseline_import import IDENTIFIED_LISTING_COLUMNS, QUOTE_COLUMNS, rows, security_code
from scripts.new_low_listing import listing_windows, listings_on

FILES = ("quotes", "calendar", "listings", "roster", "trading_status", "events")
STATUS_COLUMNS = ["date", "code", "reason", "source_url"]
EVENT_COLUMNS = ["date", "code", "event_type", "successor_code", "source_url"]
REASONS = {"announced_stop", "company_action_stop", "activity_without_close",
           "zero_reported_activity", "source_missing", "unconfirmed"}
EVENT_TYPES = set(RULES) | {"face_value_change", "share_conversion"}


def https(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and bool(parsed.hostname)


def index_records(raw, columns, sessions, field, allowed, *, multiple_kinds=False):
    result = {}
    for row in rows(raw, columns):
        key = (row["date"], row["code"])
        if multiple_kinds:
            key += (row[field],)
        if (key in result or key[0] not in sessions or not security_code(key[1])
                or row[field] not in allowed or not https(row["source_url"])):
            raise ValueError(f"invalid or duplicate {field} row: {key}")
        result[key] = row
    return result


def review(report, metadata, files, *, history, alternative, event_cases, local_gaps):
    if set(files) != set(FILES):
        raise ValueError("delivery bundle must contain all named CSV files")
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    if hashes != metadata["bundle_sha256"]:
        raise ValueError("bundle SHA-256 differs from received data")
    anchor = metadata["adjustment_anchor_date"]
    if (date.fromisoformat(anchor).isoformat() != anchor
            or not report["market_dates"][-1] <= anchor <= metadata["exported_on"]):
        raise ValueError("invalid adjustment anchor date")
    if (metadata["origin"] not in ("external", "synthetic")
            or any(not metadata.get(field, "").strip()
                   for field in ("upstream_source", "usage_basis", "usage_limits"))):
        raise ValueError("bundle requires origin, upstream source and license scope")
    if any(not metadata["corporate_action_rules"].get(kind, "").strip()
           for kind in ("face_value_change", "share_conversion")):
        raise ValueError("missing face-value or share-conversion adjustment method")
    dates = report["market_dates"]
    roster = check(report, dict(origin=metadata["origin"], source_url=metadata["source_url"],
                                retrieved_on=metadata["exported_on"], covered_dates=dates,
                                sha256=hashes["roster"], upstream_source=metadata["upstream_source"],
                                usage_basis=metadata["usage_basis"]), files["roster"])
    comparison = inspect(report, metadata, *(files[k] for k in ("quotes", "calendar", "listings")),
                         alternative=alternative, history=history, event_cases=event_cases)
    status = index_records(files["trading_status"], STATUS_COLUMNS, set(dates), "reason", REASONS)
    actions = index_records(files["events"], EVENT_COLUMNS, set(dates), "event_type", EVENT_TYPES,
                            multiple_kinds=True)
    actions_by_session = {}
    for pair, row in actions.items():
        successor = row["successor_code"]
        if successor and (not security_code(successor) or row["event_type"] not in ("merger", "share_conversion")):
            raise ValueError(f"unexpected successor for {pair}")
        actions_by_session.setdefault(pair[:2], []).append(row)
    quoted = {(row["date"], row["code"]) for row in rows(files["quotes"], QUOTE_COLUMNS)}
    if quoted & status.keys():
        raise ValueError("supplier declares a missing-close reason for a quoted stock")
    local = {}
    for group in local_gaps["groups"]:
        for day in dates:
            if group["first"] <= day <= group["last"]:
                key = day, group["code"]
                if key in local:
                    raise ValueError(f"overlapping local gap reasons: {key}")
                local[key] = group["reason"]
    vendor_listings = comparison["comparison"]["external_daily_listing_coverage"]
    intervals = [dict(row, delisted_on=row["delisted_on"] or None)
                 for row in rows(files["listings"], IDENTIFIED_LISTING_COLUMNS)]
    vendor_windows = listing_windows(intervals)
    security_ids = {(r["code"], r["listed_from"]): r["security_id"] for r in intervals}
    gaps = []
    for observed, coverage in zip(roster["sessions"], vendor_listings, strict=True):
        day = observed["date"]
        expected = set(observed["observed_members"])
        vendor_members = {code: security_ids[code, first]
                          for code, (first, _) in listings_on(vendor_windows, day).items()}
        if observed["observed_members"] != vendor_members:
            raise ValueError(f"daily supplier roster and listing intervals conflict on {day}")
        outside = sorted({code for d, code in status if d == day} - expected)
        if outside:
            raise ValueError(f"trading status outside supplier roster: {day} {outside}")
        missing = set(coverage["missing_active_codes"])
        local_missing = {code for d, code in local if d == day}
        differences = {}
        for code in sorted(missing | local_missing):
            pair = day, code
            actual = status.get(pair, {}).get("reason", "missing_status" if code in missing else None)
            if actual != local.get(pair):
                differences[code] = dict(local=local.get(pair), vendor=actual)
        gaps.append(dict(date=day, differences_by_code=differences,
                         quotes_outside_listings=coverage["quotes_outside_listings"],
                         unresolved_vendor_codes=sorted(code for code in missing if
                             status.get((day, code), {}).get("reason") in {None, "unconfirmed", "source_missing"})))
    local_actions = {(r["ex_date"], r["code"]): r["event_type"] for r in report["applied_events"]}
    action_review = []
    for day, code in sorted(local_actions.keys() | actions_by_session.keys()):
        pair = day, code
        vendor = actions_by_session.get(pair, [])
        kind = local_actions.get(pair)
        if [kind] != [event["event_type"] for event in vendor]:
            action_review.append(dict(date=day, code=code, local_event_type=kind, vendor_events=vendor))
    blockers = {
        "unresolved_vendor_gap_pairs": sum(len(row["unresolved_vendor_codes"]) for row in gaps),
        "quote_pairs_outside_listings": sum(len(row["quotes_outside_listings"]) for row in gaps),
        "missing_local_research_dates": comparison["comparison"]["unevaluated_research_dates"],
        "event_types_without_comparable_sample": comparison["event_types_without_sample"],
        "missing_alternative_basis": alternative is None,
    }
    comparisons_pending = {
        "sessions_with_listing_disagreement": len(comparison["listing_disagreement"]),
        "sessions_with_low_or_eligibility_disagreement": sum(
            bool(row["disagreement_by_code"]) for row in comparison["comparison"]["sessions"]),
        "sessions_with_missing_external_eligible_closes": sum(
            bool(row["missing_external_codes"]) for row in comparison["comparison"]["sessions"]),
        "unreconciled_event_inventory_rows": len(action_review),
        "sessions_with_price_movement_differences": sum(
            bool(row["differences_by_code"]) for row in comparison["price_movement_checks"]),
        "price_basis_sample_differences": sum(
            row["status"] == "price_basis_difference" for row in comparison["event_price_checks"]),
    }
    return dict(origin=metadata["origin"], file_sha256=hashes, adjustment_anchor_date=anchor,
                roster=roster, quote_and_low_comparison=comparison, gap_differences=gaps,
                action_inventory_review=action_review, licensing_review="REVIEW",
                intake_status="BLOCKED" if any(blockers.values()) else
                              "REVIEW" if any(comparisons_pending.values()) else "PASS",
                intake_blockers=blockers, comparison_review_counts=comparisons_pending,
                independence_review="synthetic_only" if metadata["origin"] == "synthetic" else "REVIEW",
                market_baseline_verified=False, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("report", "alternative", "history", "event_cases", "local_gaps", "metadata", "directory"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    def read(name):
        return json.loads(getattr(args, name).read_bytes())
    result = review(read("report"), read("metadata"),
                    {name: (args.directory / f"{name}.csv").read_bytes() for name in FILES},
                    history=read("history"), alternative=read("alternative"),
                    event_cases=read("event_cases"), local_gaps=read("local_gaps"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
