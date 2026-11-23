"""Compare stock-level lows with an external adjusted-close export."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from scripts.new_low_listing import listing_windows, listings_on
from scripts.new_low_adjusted_audit import STRICT_SESSIONS


def compare(report, baseline):
    if report.get("quote_policy", STRICT_SESSIONS) != STRICT_SESSIONS:
        raise ValueError("external comparator requires the strict market-session policy")
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

    external_listings = listing_windows(baseline['listings']) if 'listings' in baseline else None
    daily_coverage = []
    if external_listings is not None:
        for day in dates:
            active = listings_on(external_listings, day)
            quoted = adjusted.get(day, {})
            daily_coverage.append({
                "date": day, "active_listings": len(active), "quoted_active": len(active.keys() & quoted.keys()),
                "missing_active_codes": sorted(active.keys() - quoted.keys()),
                "quotes_outside_listings": sorted(quoted.keys() - active.keys()),
            })
    results = []
    positions = {day: i for i, day in enumerate(dates)}
    lookback = report["lookback"]
    if not isinstance(lookback, int) or not 1 <= lookback < len(dates):
        raise ValueError("invalid research lookback")
    evaluated = [r["date"] for r in report["sessions"]]
    if len(set(evaluated)) != len(evaluated) or set(evaluated) - set(dates[lookback:]):
        raise ValueError("invalid or duplicate research session")
    missing_sessions = sorted(set(dates[lookback:]) - set(evaluated))
    for row in report["sessions"]:
        day = row["date"]
        i = positions[day]
        window = dates[i - report["lookback"]:i]
        if len(window) != report["lookback"]:
            raise ValueError("baseline lacks the complete lookback")
        local_lows = set(row["adjusted_low_codes"])
        if not local_lows <= set(row["eligible_codes"]):
            raise ValueError("local low outside research cohort")
        comparable, missing, external_lows = set(), set(), set()
        local_eligible = set(row["eligible_codes"])
        full_window = [*window, day]
        coverage = {}
        candidates = local_eligible
        if external_listings is not None:
            active = listings_on(external_listings, day)
            external_eligible = {
                code for code, (start, _) in active.items()
                if start <= window[0] and all(code in adjusted.get(d, {}) for d in full_window)
            }
            candidates = external_eligible & local_eligible
            exclusions = {}
            for code in sorted((local_eligible | active.keys()) - external_eligible):
                if code not in active:
                    reason = "outside_external_listing"
                elif active[code][0] > window[0]:
                    reason = "insufficient_continuous_listing"
                elif code not in adjusted.get(day, {}):
                    reason = "missing_current_quote"
                else:
                    reason = "missing_prior_quote"
                exclusions[code] = reason
            coverage = {
                "external_exclusion_reason_by_code": exclusions,
                "external_eligible_count": len(external_eligible),
                "external_only_eligible_codes": sorted(external_eligible - local_eligible),
                "local_only_eligible_codes": sorted(local_eligible - external_eligible),
                "external_low_count": sum(
                    adjusted[day][code] < min(adjusted[d][code] for d in window)
                    for code in external_eligible),
            }
        for code in local_eligible:
            values = [adjusted.get(session, {}).get(code) for session in full_window]
            if None in values:
                missing.add(code)
                continue
            if code not in candidates:
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
            **coverage,
        })
    return {
        "provider": baseline["provider"],
        "source_url": baseline["source_url"],
        "adjustment_method": baseline["adjustment_method"],
        "sessions": results,
        "unevaluated_research_dates": missing_sessions,
        "complete_agreement_on_research_cohort": bool(results) and not missing_sessions and all(
            row["comparable"] and not any(row[k] for k in (
                "missing_external_codes", "external_only_low_codes", "local_only_low_codes"))
            and not row.get("local_only_eligible_codes")
            for row in results),
        "external_daily_listing_coverage": daily_coverage,
        "external_listing_intervals_supplied": external_listings is not None,
        "export_provenance": {key: baseline[key] for key in ("data_origin", "usage_basis", "sha256")
                              if key in baseline},
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
