"""Research-only duplicate and identity audit of extracted TWSE events."""
import json
from collections import defaultdict
from pathlib import Path
from scripts.twse_event_extract import extract_candidates


def audit_archive(directory):
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    by_key = defaultdict(list)
    failed = []
    parsed = 0
    for entry in manifest["entries"]:
        month = entry["month"]
        if entry["status"] != "downloaded_unverified":
            failed.append({"month": month, "reason": "download_failed"})
            continue
        try:
            payload = json.loads((root / entry["file"]).read_text(encoding="utf-8-sig"))
            events = extract_candidates(payload, entry["source_url"])
            for event in events:
                if event["ex_date"][:7] != month:
                    raise ValueError("candidate date outside requested month")
                key = (event["code"], event["ex_date"])
                by_key[key].append(event)
            parsed += len(events)
        except (ValueError, KeyError, TypeError) as exc:
            failed.append({"month": month, "reason": str(exc)[:200]})
    duplicates = []
    conflicts = []
    for (code, day), events in sorted(by_key.items()):
        if len(events) < 2:
            continue
        versions = {(e["prior_close"], e["reference_price"], e["event_type"]) for e in events}
        record = {"code": code, "ex_date": day, "rows": len(events),
                  "versions": len(versions)}
        (conflicts if len(versions) > 1 else duplicates).append(record)
    return {
        "parsed_candidates": parsed,
        "unique_code_date_keys": len(by_key),
        "duplicate_identical_keys": duplicates,
        "conflicting_keys": conflicts,
        "failed_months": failed,
        "duplicate_month_payloads": bool(manifest.get("duplicate_month_payloads")),
        "identity_audit_passed": not (failed or duplicates or conflicts or manifest.get("duplicate_month_payloads")),
        "corporate_action_completeness_verified": False,
        "score_eligible": False,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    report = audit_archive(args.directory)
    output = Path(args.directory) / "identity_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not report["identity_audit_passed"]:
        raise SystemExit(1)
