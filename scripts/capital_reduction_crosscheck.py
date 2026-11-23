"""Compare the TWSE capital-reduction inventory with a second publication."""
import argparse
import json
from pathlib import Path

from scripts.corporate_action_audit import positive


def crosscheck(primary, secondary):
    records = {}
    start, end = primary["start"], primary["end"]
    primary_rows = primary["candidates"]
    expected = {(row["code"], row["effective_date"]) for row in primary_rows}
    if len(expected) != len(primary_rows):
        raise ValueError("duplicate event in primary inventory")
    for response in secondary:
        if response.get("status") != 200 or not isinstance(response.get("data"), list):
            raise ValueError("secondary request failed")
        for row in response["data"]:
            code, day = row["stock_id"], row["date"]
            if not start <= day <= end:
                raise ValueError("secondary event outside primary window")
            if (code, day) in records:
                raise ValueError("duplicate event in secondary inventory")
            records[code, day] = row

    checks = []
    for action in primary_rows:
        key = action["code"], action["effective_date"]
        peer = records.get(key)
        prior_match = bool(peer and positive(action["pre_halt_close"])
                           == positive(peer["ClosingPriceonTheLastTradingDay"]))
        reference_match = bool(peer and positive(action["resumption_reference"])
                               == positive(peer["PostReductionReferencePrice"]))
        checks.append({
            "code": key[0], "date": key[1],
            "twse_pre_halt_close": action["pre_halt_close"],
            "twse_resumption_reference": action["resumption_reference"],
            "secondary": peer,
            "prior_close_matches": prior_match,
            "resumption_reference_matches": reference_match,
        })
    return {
        "checks": checks,
        "secondary_only_events": sorted(records.keys() - expected),
        "matching_prices": sum(row["prior_close_matches"] and row["resumption_reference_matches"]
                               for row in checks),
        # Per-code calls seeded by the TWSE inventory cannot detect missing codes.
        "full_market_coverage_verified": False,
        "score_eligible": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary", type=Path)
    parser.add_argument("secondary", type=Path)
    args = parser.parse_args()
    result = crosscheck(json.loads(args.primary.read_text()), json.loads(args.secondary.read_text()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
