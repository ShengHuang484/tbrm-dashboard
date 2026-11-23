"""Check archived-input research runs against committed stock-level results."""
import argparse
import json
from pathlib import Path


def check_replay(adjusted, expected_adjusted, sensitivity, expected_sensitivity):
    for key, expected in expected_adjusted.items():
        if key in ("archive_runs", "sessions"):
            continue
        if adjusted.get(key) != expected:
            raise ValueError(f"archive replay mismatch: {key}")
    if len(adjusted["sessions"]) != len(expected_adjusted["sessions"]):
        raise ValueError("archive replay session count mismatch")
    for actual, expected in zip(adjusted["sessions"], expected_adjusted["sessions"]):
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ValueError(f"archive replay mismatch: {expected['date']} {key}")
    if sensitivity != expected_sensitivity:
        raise ValueError("quote-policy sensitivity replay mismatch")
    if (adjusted["score_eligible"] is not False or sensitivity["score_eligible"] is not False):
        raise ValueError("research replay cannot authorize scoring")
    return {"factor_count": adjusted["factor_count"], "sessions": len(adjusted["sessions"]),
            "archive_replay_verified": True, "market_baseline_verified": False,
            "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("adjusted", "expected_adjusted", "sensitivity", "expected_sensitivity"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    reports = [json.loads(path.read_text()) for path in (
        args.adjusted, args.expected_adjusted, args.sensitivity, args.expected_sensitivity)]
    print(json.dumps(check_replay(*reports), indent=2))
