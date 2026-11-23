"""Reconcile a cross-market event list against dated venue evidence."""
import argparse
import json
from pathlib import Path


def review(history, candidates, listed, otc):
    def indexed(rows, day_field):
        result = {}
        for row in rows:
            key = row["code"], row[day_field]
            if key in result:
                raise ValueError(f"duplicate venue evidence: {key}")
            result[key] = row
        return result

    local = indexed(listed, "effective_date")
    outside = indexed(otc, "effective_date")
    if local.keys() & outside.keys():
        raise ValueError("conflicting venue claims")
    seen, results = set(), []
    for row in candidates:
        code, day = key = row["stock_id"], row["date"]
        if key in seen:
            raise ValueError(f"duplicate source event: {key}")
        seen.add(key)
        quoted = code in history.get(day, {})
        if key in local and quoted:
            status, url = "twse_included", local[key]["issuer_url"]
        elif key in outside and day in history and not quoted:
            status, url = "tpex_excluded", outside[key]["notice_url"]
        else:
            status, url = "pending_review", None
        results.append(dict(code=code, effective_date=day, status=status, source_url=url))
    return {"events": results, "evidence_without_candidate": sorted((local.keys() | outside.keys()) - seen),
            "market_completeness_verified": False, "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("--evidence-directory", type=Path, default=Path("research"))
    args = parser.parse_args()
    def read(name):
        return json.loads((args.evidence_directory / name).read_text())
    print(json.dumps(review(json.loads(args.history.read_text()),
                            read("finmind_action_crosscheck.json")["par_value_changes"],
                            read("face_value_issuers.json"), read("tpex_par_value_notices.json")),
                     indent=2))
