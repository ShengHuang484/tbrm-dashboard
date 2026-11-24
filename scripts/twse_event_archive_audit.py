"""Read and validate archived TWSE monthly JSON without approving events.

The upstream response schema is versioned implicitly; do not silently guess
which columns are ex-date, stock code or official reference price.
"""
import json
from pathlib import Path


def inspect_archive(directory):
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    reports = []
    for entry in manifest["entries"]:
        month = entry["month"]
        if entry["status"] != "downloaded_unverified":
            reports.append({"month": month, "status": "download_failed"})
            continue
        obj = json.loads((root / entry["file"]).read_text(encoding="utf-8-sig"))
        tables = obj.get("tables")
        if isinstance(tables, list):
            layouts = [{"fields": t.get("fields"), "rows": len(t.get("data", []))}
                       for t in tables if isinstance(t, dict)]
        elif isinstance(obj.get("data"), list):
            layouts = [{"fields": obj.get("fields"), "rows": len(obj["data"])}]
        else:
            layouts = []
        reports.append({"month": month, "status": "schema_review_required",
                        "twse_status": obj.get("stat"), "layouts": layouts})
    return {
        "months": reports,
        "schema_approved": False,
        "corporate_action_completeness_verified": False,
        "score_eligible": False,
    }
