"""Attribute observed missing closes and rank remaining gaps without imputing prices."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from scripts.new_low_listing import listing_windows, listings_on

COMPANY_ACTION_STOPS = {"1808", "8422", "7780", "6949"}
QUOTE_ACTIVITY = {"activity_without_close", "zero_reported_activity"}


def audit(history, report, lifecycle, activity, activity_source):
    dates = report["market_dates"]
    if dates != sorted(history):
        raise ValueError("research calendar does not match archived quotes")
    positions = {day: i for i, day in enumerate(dates)}
    windows = listing_windows(report["listing_intervals"])
    missing = {
        (code, day) for day in dates
        for code in listings_on(windows, day).keys() - history[day].keys()
    }
    classified = {}
    for stop in lifecycle["trading_stop_checks"]:
        if stop["conflicting_sessions"]:
            raise ValueError("cannot classify conflicting stop evidence")
        code = stop["code"]
        reason = "company_action_stop" if code in COMPANY_ACTION_STOPS or stop.get("event_type") == "capital_reduction" else "announced_stop"
        for day in stop["affected_sessions"]:
            key = code, day
            if key not in missing or key in classified:
                raise ValueError("invalid or duplicate stop evidence")
            classified[key] = reason
    if not activity_source.startswith("https://") or activity["conflicting_dates"]:
        raise ValueError("invalid quote activity provenance")
    for day, reason in activity["absent_close_reason"].items():
        key = activity["code"], day
        if key not in missing or key in classified or reason not in QUOTE_ACTIVITY:
            raise ValueError("invalid or overlapping quote activity evidence")
        classified[key] = reason

    if len(missing) != lifecycle["coverage"]["missing_close_pairs"]:
        raise ValueError("missing-close denominator differs from historical replay")
    candidates = defaultdict(list)
    blockers = defaultdict(set)
    excluded_by_listing = {}
    for row in report["sessions"]:
        day = row["date"]
        start = dates[positions[day] - report["lookback"]]
        active = listings_on(windows, day)
        eligible = set(row["eligible_codes"])
        excluded_by_listing[day] = dict(
            insufficient_listing_age=sum(interval[0] > start for interval in active.values()),
            past_exit=sum(any(end and end <= day for _, end in intervals) and code not in active
                          for code, intervals in windows.items()))
        for code, interval in active.items():
            if interval[0] > start:
                continue
            if code in eligible:
                continue
            for index in range(positions[start], positions[day] + 1):
                gap_day = dates[index]
                if (key := (code, gap_day)) in missing:
                    candidates[key].append(day)
                    blockers[code, day].add(gap_day)

    summary = {}
    groups = []
    for code, day in sorted(missing):
        reason = classified.get((code, day), "unknown")
        stats = summary.setdefault(reason, {"codes": set(), "pairs": 0})
        stats["codes"].add(code)
        stats["pairs"] += 1
        if (not groups or groups[-1]["code"] != code or groups[-1]["reason"] != reason
                or positions[day] != positions[groups[-1]["last"]] + 1):
            groups.append(dict(code=code, reason=reason, first=day, last=day, pairs=0,
                               study_dates=set(), sole_gap_study_dates=[]))
        group = groups[-1]
        group["last"] = day
        group["pairs"] += 1
        group["study_dates"].update(candidates[code, day])
    for group in groups:
        group["study_dates"] = sorted(group["study_dates"])
        group["sole_gap_study_dates"] = [
            day for day in group["study_dates"]
            if all(group["first"] <= gap <= group["last"] for gap in blockers[group["code"], day])
        ]
    groups.sort(key=lambda g: (g["reason"] != "unknown", -len(g["sole_gap_study_dates"]),
                               -len(g["study_dates"]), -g["pairs"], g["code"], g["first"]))
    event_leads = {(r["code"], r["ex_date"]): r for r in report.get("applied_events", [])
                   if r["event_type"] in ("capital_reduction", "split", "reverse_split")}
    possible_action_stops = []
    for group in groups:
        next_position = positions[group["last"]] + 1
        if group["reason"] != "unknown" or next_position == len(dates):
            continue
        next_session = dates[next_position]
        event = event_leads.get((group["code"], next_session))
        if event is not None:
            possible_action_stops.append(dict(group, observed_resumption=next_session,
                event_type=event["event_type"], event_source=event["source_url"],
                verification_needed="dated stop or share-replacement notice"))
    unknown_groups = [g for g in groups if g["reason"] == "unknown"]
    priority_queue = [
        dict(code=g["code"], first=g["first"], last=g["last"], pairs=g["pairs"],
             impacted_study_dates=g["study_dates"],
             sole_gap_study_dates=g["sole_gap_study_dates"],
             priority="critical" if g["sole_gap_study_dates"] else
                      "high" if g["study_dates"] else "historical",
             verification_needed="dated primary-source listing, trade-status or quote evidence")
        for g in unknown_groups
    ]
    if sum(v["pairs"] for v in summary.values()) != len(missing):
        raise ValueError("missing-close classification partition is incomplete")
    return dict(
        unknown_priority_queue=priority_queue,
        unknown_group_count=len(unknown_groups),
        unknown_pairs=sum(g["pairs"] for g in unknown_groups),
        possible_action_stops=possible_action_stops,
        classification={reason: dict(stocks=len(stats["codes"]), pairs=stats["pairs"])
                        for reason, stats in sorted(summary.items())},
        study_day_impact=[dict(date=row["date"], excluded_with_missing_close=sum(
            target == row["date"] for _, target in blockers), known_lows=row["adjusted_low_count"],
            unknown_only_exclusions=sum(target == row["date"] and
                all((code, gap) not in classified for gap in gaps)
                for (code, target), gaps in blockers.items()))
            | excluded_by_listing[row["date"]] for row in report["sessions"]],
        groups=groups, quote_activity_source=activity_source, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("history", "report", "lifecycle", "activity", "sources"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    payloads = {arg: getattr(args, arg).read_bytes()
                for arg in ("history", "report", "lifecycle", "activity", "sources")}
    history, report, lifecycle, activity, sources = map(json.loads, payloads.values())
    result = audit(history, report, lifecycle, activity["quote_activity"], sources["quote_source"])
    result["source_artifact_sha256"] = activity["raw_sha256"]
    result["input_sha256"] = {k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()}
    if args.summary:
        groups = result.pop("groups")
        result.update(group_count=len(groups), highest_priority_unknowns=[
            g for g in groups if g["reason"] == "unknown"][:10])
        result["unknown_priority_queue"] = result["unknown_priority_queue"][:20]
        result["priority_queue_truncated"] = result["unknown_group_count"] > 20
    print(json.dumps(result, ensure_ascii=False, indent=2))
