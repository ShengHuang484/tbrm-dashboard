"""Research-only audit of the 262-day raw-close stock universe.

Checks date ordering, positive finite prices and per-day symbol coverage.
Does not certify listed-stock universe completeness or adjusted-price validity.
"""
import json
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


def audit_history(history, required_days=262):
    if not isinstance(history, dict):
        raise ValueError("history must be date -> code/close mapping")
    dates = sorted(history)
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate dates")
    counts = {}
    invalid = []
    all_codes = set()
    common = None
    for day in dates:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("invalid date")
        prices = history[day]
        if not isinstance(prices, dict):
            raise ValueError("invalid daily stock mapping")
        codes = set(prices)
        all_codes.update(codes)
        common = codes if common is None else common & codes
        counts[day] = len(codes)
        for code, value in prices.items():
            if not (isinstance(code, str) and len(code) == 4 and code.isdigit() and code[0] != "0"):
                invalid.append({"date": day, "code": str(code), "reason": "invalid_code"})
                continue
            try:
                price = Decimal(str(value))
                if not price.is_finite() or price <= 0:
                    raise ValueError("nonpositive or nonfinite")
            except (InvalidOperation, ValueError, TypeError):
                invalid.append({"date": day, "code": code, "reason": "invalid_close"})
    common = common or set()
    changing = sorted(all_codes - common)
    return {
        "trading_days": len(dates),
        "required_days": required_days,
        "date_window": [dates[0], dates[-1]] if dates else [],
        "min_daily_codes": min(counts.values()) if counts else 0,
        "max_daily_codes": max(counts.values()) if counts else 0,
        "unique_codes": len(all_codes),
        "full_window_codes": len(common),
        "variable_coverage_codes": len(changing),
        "variable_coverage_sample": changing[:30],
        "invalid_close_count": len(invalid),
        "invalid_close_sample": invalid[:30],
        "raw_history_structurally_valid": len(dates) == required_days and not invalid and bool(common),
        "listed_stock_universe_verified": False,
        "adjusted_prices_verified": False,
        "score_eligible": False,
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("history")
    p.add_argument("output")
    args = p.parse_args()
    report = audit_history(json.loads(Path(args.history).read_text()))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    if not report["raw_history_structurally_valid"]:
        raise SystemExit("Raw stock close history failed structural audit")
