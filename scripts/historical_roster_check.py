"""Compare dated ordinary-share membership with the internal listing reconstruction."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from scripts.new_low_baseline_import import rows, security_code
from scripts.new_low_listing import listing_windows, listings_on

COLUMNS = ["date", "code", "security_id"]
ORIGINS = {"twse", "external", "synthetic"}


def check(report, manifest=None, roster=None):
    dates = report["market_dates"]
    if not dates or dates != sorted(set(dates)):
        raise ValueError("expected ordered, unique market dates")
    observations = {}
    if (manifest is None) != (roster is None):
        raise ValueError("roster and source manifest are required together")
    if manifest is not None:
        origin = manifest["origin"]
        if origin not in ORIGINS:
            raise ValueError("unrecognized roster origin")
        url = urlsplit(manifest["source_url"])
        collected = manifest["retrieved_on"]
        declared = manifest["covered_dates"]
        if (url.scheme != "https" or not url.hostname
                or date.fromisoformat(collected).isoformat() != collected):
            raise ValueError("invalid roster source provenance")
        if origin == "external" and (not manifest.get("usage_basis", "").strip()
                                     or not manifest.get("upstream_source", "").strip()):
            raise ValueError("external roster requires upstream and usage declarations")
        if declared != sorted(set(declared)) or not set(declared) <= set(dates):
            raise ValueError("duplicate or extra roster date")
        if not declared or collected < declared[-1]:
            raise ValueError("invalid roster acquisition cutoff")
        if hashlib.sha256(roster).hexdigest() != manifest["sha256"]:
            raise ValueError("roster SHA-256 differs from delivery")
        observations = {day: {} for day in declared}
        identifiers = {day: set() for day in declared}
        for row in rows(roster, COLUMNS):
            day, code, identity = (row[field] for field in COLUMNS)
            if day not in observations or not security_code(code) or not identity.strip() or identity != identity.strip():
                raise ValueError("invalid or out-of-scope daily membership")
            if code in observations[day] or identity in identifiers[day]:
                raise ValueError("duplicate code or security_id on roster date")
            observations[day][code] = identity
            identifiers[day].add(identity)
        if any(not members for members in observations.values()):
            raise ValueError("declared roster date has no members")
    known = listing_windows(report["listing_intervals"])
    days = []
    previous = None
    for day in dates:
        local = listings_on(known, day)
        observed = observations.get(day)
        row = dict(date=day, reconstructed_codes=sorted(local), observed_members=None,
                   reconstructed_only=None, observed_only=None, adjacent_changes=None)
        if observed is not None:
            row.update(observed_members=dict(sorted(observed.items())),
                       reconstructed_only=sorted(local.keys() - observed.keys()),
                       observed_only=sorted(observed.keys() - local.keys()))
            if previous is not None:
                before = {identity: code for code, identity in previous.items()}
                after = {identity: code for code, identity in observed.items()}
                row["adjacent_changes"] = dict(
                    entered=sorted(observed.keys() - previous.keys()),
                    exited=sorted(previous.keys() - observed.keys()),
                    reused_codes=sorted(code for code in previous.keys() & observed.keys()
                                        if previous[code] != observed[code]),
                    ticker_transitions=[dict(security_id=i, previous_code=before[i], current_code=after[i])
                                        for i in sorted(before.keys() & after.keys()) if before[i] != after[i]],
                )
        days.append(row)
        previous = observed
    unknown_ranges = []
    for index, day in enumerate(dates):
        if day not in observations:
            if index and dates[index - 1] not in observations:
                unknown_ranges[-1]["last"] = day
                unknown_ranges[-1]["sessions"] += 1
            else:
                unknown_ranges.append(dict(first=day, last=day, sessions=1))
    differences = sum(bool(row["observed_only"] or row["reconstructed_only"]) for row in days)
    return dict(status="BLOCKED" if not observations else "REVIEW" if differences else "PARTIAL",
                provenance=manifest, observed_sessions=len(observations), expected_sessions=len(dates),
                sessions_with_membership_differences=differences, unconfirmed_ranges=unknown_ranges,
                sessions=days, independent_universe_verified=False, score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--roster", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    result = check(json.loads(args.report.read_bytes()),
                   json.loads(args.manifest.read_bytes()) if args.manifest else None,
                   args.roster.read_bytes() if args.roster else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
