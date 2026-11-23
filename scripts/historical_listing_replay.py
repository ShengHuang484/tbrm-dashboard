"""Replay research using a bounded listing reconstruction with dated exit evidence."""
import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path

from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_listing import listing_windows, listings_on
from scripts.new_low_replay_check import membership_digest
from scripts.new_low_rights_scenario import TWSE_REFERENCE, ZERO_RIGHTS, select_events


def audit_stops(history, windows, stops, events=()):
    results = []
    for stop in stops:
        code, start, end = (stop[k] for k in ("code", "start", "end"))
        if (any(date.fromisoformat(d).isoformat() != d for d in (start, end))
                or start >= end or not stop["sources"]
                or any(not url.startswith("https://") for url in stop["sources"])):
            raise ValueError("invalid trading stop evidence")
        if "published_evidence" in stop:
            published = stop["published_evidence"]
            normalized = json.dumps(published, sort_keys=True, separators=(",", ":")).encode()
            if (hashlib.sha256(normalized).hexdigest() != stop["normalized_evidence_sha256"]
                    or tuple(published[k] for k in ("code", "start", "end")) != (code, start, end)
                    or published["source_url"] not in stop["sources"]):
                raise ValueError("stop evidence does not match normalized source facts")
        if "event_type" in stop and not any(
                (e["code"], e["ex_date"], e["event_type"]) == (code, end, stop["event_type"])
                for e in events):
            raise ValueError("no archived corporate action at the documented restoration date")
        active = listings_on(windows, start).get(code)
        disposition = stop["disposition"]
        if active is None or disposition not in ("resume", "delist"):
            raise ValueError("stop requires an active listing and known disposition")
        if disposition == "delist" and active[1] != end:
            raise ValueError("stop does not end at the documented delisting")
        if disposition == "resume" and listings_on(windows, end).get(code) != active:
            raise ValueError("resumption crosses listing identity")
        sessions = sorted(day for day in history if start <= day < end)
        conflicts = [d for d in sessions if code in history[d]]
        if disposition == "resume" and end in history and code not in history[end]:
            conflicts.append(end)
        result = dict(code=code, disposition=disposition, affected_sessions=sessions,
                      conflicting_sessions=conflicts)
        if "event_type" in stop:
            result["event_type"] = stop["event_type"]
        results.append(result)
    return results


def replay(history, adjusted, roster, evidence, *, strict_report=False, listings_archive=None,
           rights_basis=TWSE_REFERENCE, rights_evidence=None):
    dates = sorted(history)
    if evidence["snapshot_date"] < dates[-1]:
        raise ValueError("snapshot predates research endpoint")
    if len({row["code"] for row in roster}) != len(roster):
        raise ValueError("duplicate snapshot code")
    receipts = {row["code"] for row in roster if row["industry"] == "91"}
    listings = [dict(code=row["code"], listed_from=row["listed_from"], delisted_on=None)
                for row in roster if row["code"] not in receipts]
    exits = evidence["historical_exits"]
    if any(not all(row.get(k, "").startswith("https://")
                   for k in ("listing_source", "exit_source")) for row in exits):
        raise ValueError("historical exits require listing and exit sources")
    listings.extend(exits)
    windows = listing_windows(listings)
    ordinary = {day: {code: close for code, close in quotes.items() if code not in receipts}
                for day, quotes in history.items()}
    events = select_events([row for row in adjusted["applied_events"] if row["code"] not in receipts],
                           rights_basis, rights_evidence)
    conflicts = {}
    for day, quotes in ordinary.items():
        outside = sorted(quotes.keys() - listings_on(windows, day).keys())
        if outside:
            conflicts[day] = outside
    stops = audit_stops(ordinary, windows, evidence.get("trading_stops", []), events)
    stop_conflicts = any(row["conflicting_sessions"] for row in stops)
    if conflicts or stop_conflicts:
        if strict_report:
            raise ValueError(f"quotes outside reconstructed listing or trading intervals: {conflicts}, {stops}")
        return dict(outside_listing_quotes=conflicts, trading_stop_checks=stops,
                    listing_universe_verified=False,
                    score_eligible=False)
    documented = {(r["code"], d) for r in stops for d in r["affected_sessions"]}
    active_pairs = missing_pairs = 0
    unresolved = {}
    for day, quotes in ordinary.items():
        active = listings_on(windows, day)
        absent = active.keys() - quotes.keys()
        active_pairs += len(active)
        missing_pairs += len(absent)
        for code in sorted(absent):
            if (code, day) not in documented:
                unresolved.setdefault(code, []).append(day)
    coverage = dict(reconstructed_active_pairs=active_pairs, missing_close_pairs=missing_pairs,
                    documented_stop_pairs=len(documented),
                    unclassified_absence_pairs=missing_pairs - len(documented),
                    unclassified_absence_dates=unresolved)
    if listings_archive is not None:
        if listings_archive["date_window"] != [dates[0], dates[-1]]:
            raise ValueError("new listing archive differs from the research window")
        expected = {(r["code"], r["listed_from"]) for r in listings
                    if dates[0] <= r["listed_from"] <= dates[-1]}
        reported = {(r["code"], r["listed_from"])
                    for r in listings_archive["new_listing_observations"]}
        coverage["archive_new_listing_matches"] = len(expected & reported)
        coverage["reconstructed_starts_without_archive"] = sorted(expected - reported)
        coverage["archived_starts_without_reconstruction"] = sorted(reported - expected)
    result = audit_adjusted_lows(ordinary, events, adjusted["lookback"], listings=listings)
    if strict_report:
        result.update(applied_events=events, rights_basis=rights_basis, listing_intervals=listings,
                      issuer_snapshot_date=evidence["snapshot_date"],
                      historical_exit_codes=sorted({row["code"] for row in exits}))
        return result
    return dict(snapshot_date=evidence["snapshot_date"], rights_basis=rights_basis, market_sessions=len(dates),
                historical_exit_codes=sorted({row["code"] for row in exits}),
                factor_count=result["factor_count"], outside_listing_quotes={}, trading_stop_checks=stops,
                coverage=coverage,
                sessions=[dict(date=row["date"], eligible=row["strict_eligible"],
                               lows=row["adjusted_low_count"], active=row["active_listings"],
                               unquoted_current=row["unquoted_current_listings"],
                               membership_sha256=membership_digest(row))
                          for row in result["sessions"]],
                listing_universe_verified=False, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "adjusted", "roster", "evidence"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--strict-report", action="store_true")
    parser.add_argument("--listings-archive", type=Path)
    parser.add_argument("--rights-basis", choices=(TWSE_REFERENCE, ZERO_RIGHTS), default=TWSE_REFERENCE)
    parser.add_argument("--rights-evidence", type=Path)
    args = parser.parse_args()
    with args.roster.open(newline="") as roster:
        result = replay(json.loads(args.history.read_text()), json.loads(args.adjusted.read_text()),
                        list(csv.DictReader(roster)), json.loads(args.evidence.read_text()),
                        strict_report=args.strict_report,
                        listings_archive=json.loads(args.listings_archive.read_text())
                        if args.listings_archive else None,
                        rights_basis=args.rights_basis,
                        rights_evidence=json.loads(args.rights_evidence.read_text())
                        if args.rights_evidence else None)
    print(json.dumps(result, indent=2))
