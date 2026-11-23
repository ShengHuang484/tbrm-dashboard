"""Read and reconcile archived TWT49U monthly reports for research."""
import hashlib
import json
from zipfile import ZipFile

from scripts.corporate_action_audit import positive
from scripts.twse_event_extract import extract_candidates


def load_months(paths, market_dates):
    expected = {day[:7] for day in market_dates}
    records, hashes = [], {}
    for path in paths:
        with ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for entry in manifest["entries"]:
                month = entry["month"]
                if month not in expected:
                    continue
                if month in hashes or entry["status"] != "downloaded_unverified":
                    raise ValueError(f"duplicate or failed month: {month}")
                raw = archive.read(entry["file"])
                digest = hashlib.sha256(raw).hexdigest()
                if digest != entry["sha256"]:
                    raise ValueError(f"archive digest mismatch: {month}")
                candidates = extract_candidates(json.loads(raw), entry["source_url"])
                if any(not row["ex_date"].startswith(month + "-") for row in candidates):
                    raise ValueError(f"candidate outside archive month: {month}")
                records.extend(candidates)
                hashes[month] = digest
    if hashes.keys() != expected:
        raise ValueError("archives omit required market months")
    return records, hashes


def reconcile_months(history, records, ex_right, existing):
    days = sorted(history)
    prior_days = dict(zip(days[1:], days))
    replaced = {(row["code"], row["reported_date"]): row for row in ex_right["cases"]}
    existing_keys = {(r["code"], r["ex_date"]) for r in existing}
    events, excluded, seen = [], [], set()
    for row in records:
        code, day = row["code"], row["ex_date"]
        if not days[0] <= day <= days[-1]:
            continue
        key = code, day
        if key in seen:
            raise ValueError(f"duplicate monthly event: {key}")
        seen.add(key)
        if key in replaced:
            case = replaced[key]
            if (positive(row["prior_close"]) != positive(case["prior_close"])
                    or positive(row["reference_price"]) != positive(case["reference"])):
                raise ValueError(f"reconciled anomaly disagrees with monthly archive: {key}")
            reason = "replaced_by_reconciled_session"
        elif key in existing_keys:
            raise ValueError(f"overlapping monthly and assembled action requires review: {key}")
        elif day == days[0]:
            reason = "first_archive_session"
        elif day not in prior_days:
            reason = "not_an_archived_market_session"
        elif code not in history[day]:
            reason = "no_effective_day_close"
        elif code not in history[prior_days[day]]:
            reason = "no_preceding_session_close"
        elif positive(row["prior_close"]) != positive(history[prior_days[day]][code]):
            reason = "prior_close_mismatch"
        else:
            events.append(dict(row, verified=True, event_type="monthly_ex_right_reconciled",
                               verification_note="official reference and prior quote agree for research"))
            continue
        excluded.append({"code": code, "date": day, "reason": reason})
    if not replaced.keys() <= seen:
        raise ValueError("reconciled anomalies missing from monthly archive")
    return events, excluded
