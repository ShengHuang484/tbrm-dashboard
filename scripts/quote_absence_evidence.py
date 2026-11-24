"""Distinguish an announced halt from turnover with no published close."""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path


def reconcile_quotes(history, code, payload):
    if payload.get("status") != 200:
        raise ValueError("daily quote query failed")
    rows = {}
    for row in payload["data"]:
        day = row["date"]
        if row["stock_id"] != code or day in rows or day not in history:
            raise ValueError("unexpected quote identity or session")
        rows[day] = row
    if rows.keys() != history.keys():
        raise ValueError("incomplete provider calendar")
    gaps, conflicts = {}, []
    for day, row in sorted(rows.items()):
        close = Decimal(str(row["close"]))
        volume, trades = row["Trading_Volume"], row["Trading_turnover"]
        if not close.is_finite() or close < 0 or min(volume, trades) < 0:
            raise ValueError("invalid quote evidence")
        raw = history[day].get(code)
        if raw is None and close == 0:
            gaps[day] = ("activity_without_close" if volume or trades else "zero_reported_activity")
        elif raw is None or close != Decimal(str(raw)):
            conflicts.append(day)
    return dict(code=code, sessions=len(rows), matched_positive_closes=len(rows)-len(gaps)-len(conflicts),
                absent_close_reason=gaps, conflicting_dates=conflicts)


def check_halt(history, notice):
    code = notice["code"]
    start, resume = notice["stop_from"], notice["resumption_date"]
    if start >= resume:
        raise ValueError("invalid suspension boundary")
    prior = max((d for d in history if d < start and code in history[d]), default=None)
    dates = sorted(d for d in history if start <= d < resume)
    if prior != notice["last_pre_stop_date"] or prior is None:
        raise ValueError("invalid pre-stop quote date")
    if Decimal(str(history[prior][code])) != Decimal(notice["pre_stop_close"]):
        raise ValueError("invalid pre-stop close")
    return dict(code=code, absent_during_stop=[d for d in dates if code not in history[d]],
                conflicting_dates=[d for d in dates if code in history[d]],
                resumption_in_archive=resume in history, last_pre_stop_date=prior)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "finmind_response", "evidence"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    history = json.loads(args.history.read_text())
    evidence = json.loads(args.evidence.read_text())
    raw = args.finmind_response.read_bytes()
    result = dict(quote_activity=reconcile_quotes(history, evidence["quote_code"], json.loads(raw)),
                  halt=check_halt(history, evidence["halt_notice"]),
                  raw_sha256=hashlib.sha256(raw).hexdigest(), score_eligible=False)
    print(json.dumps(result, indent=2))
