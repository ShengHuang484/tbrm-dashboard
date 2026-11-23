"""Compare stock-level lows with an external adjusted-close export."""
import argparse
import json
from decimal import Decimal
from pathlib import Path


def compare(report, baseline):
    for field in ("provider", "source_url", "adjustment_method"):
        if not isinstance(baseline.get(field), str) or not baseline[field].strip():
            raise ValueError(f"missing baseline provenance: {field}")
    if not baseline["source_url"].startswith("https://"):
        raise ValueError("baseline source URL must use HTTPS")
    all_dates = baseline["market_dates"]
    if all_dates != sorted(set(all_dates)):
        raise ValueError("baseline market dates must be sorted and unique")
    dates = report["market_dates"]
    if all_dates != dates:
        raise ValueError("baseline market calendar differs from research calendar")
    observations = baseline["adjusted_closes"]
    if observations.keys() - set(dates):
        raise ValueError("baseline observations outside market calendar")
    adjusted = {}
    for day, prices in observations.items():
        adjusted[day] = {code: Decimal(str(price)) for code, price in prices.items()}
        if any(not price.is_finite() or price <= 0 for price in adjusted[day].values()):
            raise ValueError(f"invalid baseline close: {day}")

    results = []
    positions = {day: i for i, day in enumerate(dates)}
    for row in report["sessions"]:
        day = row["date"]
        i = positions[day]
        window = dates[i - report["lookback"]:i]
        if len(window) != report["lookback"]:
            raise ValueError("baseline lacks the complete lookback")
        local_lows = set(row["adjusted_low_codes"])
        comparable, missing, external_lows = set(), set(), set()
        for code in row["eligible_codes"]:
            values = [adjusted.get(session, {}).get(code) for session in [*window, day]]
            if None in values:
                missing.add(code)
                continue
            comparable.add(code)
            if values[-1] < min(values[:-1]):
                external_lows.add(code)
        results.append({
            "date": day,
            "comparable": len(comparable),
            "missing_external_codes": sorted(missing),
            "external_low_count_on_comparable": len(external_lows),
            "local_low_count_on_comparable": len(local_lows & comparable),
            "external_only_low_codes": sorted(external_lows - local_lows),
            "local_only_low_codes": sorted((local_lows & comparable) - external_lows),
        })
    return {
        "provider": baseline["provider"],
        "source_url": baseline["source_url"],
        "adjustment_method": baseline["adjustment_method"],
        "sessions": results,
        "complete_agreement_on_research_cohort": bool(results) and all(
            row["comparable"] and not any(row[k] for k in (
                "missing_external_codes", "external_only_low_codes", "local_only_low_codes"))
            for row in results),
        "market_baseline_verified": False,
        "score_eligible": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("baseline", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(json.loads(args.report.read_text()),
                             json.loads(args.baseline.read_text())), ensure_ascii=False, indent=2))
