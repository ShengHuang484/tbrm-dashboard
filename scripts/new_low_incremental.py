"""Advance a research-only rolling close archive using dated evidence."""
import argparse
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.corporate_action_audit import positive
from scripts.external_delivery_bundle import REASONS
from scripts.new_low_adjusted_audit import audit_adjusted_lows
from scripts.new_low_baseline_import import security_code
from scripts.new_low_listing import listing_windows, listings_on

QUOTE_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999&date="


def iso(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("expected an ISO calendar date")
    return parsed


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_evidence(kind, spec, read):
    raw = read(kind)
    source = urlsplit(spec["source_url"])
    if source.scheme != "https" or not source.hostname or digest(raw) != spec["sha256"]:
        raise ValueError(f"source metadata or digest mismatch: {kind}")
    return json.loads(raw)


def parse_closes(payload, day):
    if payload.get("stat") != "OK" or payload.get("date") != day.replace("-", ""):
        raise ValueError("dated quote report is delayed or mismatched")
    tables = list(payload.get("tables", []))
    for key, rows in payload.items():
        if re.fullmatch(r"data[0-9]*", key):
            tables.append(dict(fields=payload.get("fields" + key[4:], []), data=rows))
    prices = {}
    for table in tables:
        fields = table.get("fields", [])
        if not {"證券代號", "收盤價"} <= set(fields):
            continue
        if len(set(fields)) != len(fields):
            raise ValueError("duplicate quote fields")
        for raw in table["data"]:
            row = dict(zip(fields, raw, strict=True))
            code, close = row["證券代號"].strip(), row["收盤價"].strip().replace(",", "")
            if not security_code(code):
                continue
            value = None if close in {"--", "---", ""} else str(positive(close))
            if code in prices and prices[code] != value:
                raise ValueError(f"conflicting official close: {code}")
            prices[code] = value
    if not prices:
        raise ValueError("dated quote table is empty")
    return prices


def seed(history, report, gap_audit, retention=262):
    dates = report["market_dates"]
    if sorted(history) != dates or len(dates) > retention or not report["lookback"] < retention:
        raise ValueError("seed requires aligned research history and retention")
    if report.get("score_eligible") is not False:
        raise ValueError("seed requires a research-only report")
    listings = report["listing_intervals"]
    windows = listing_windows(listings)
    ordinary = {}
    gaps = {day: {} for day in dates}
    for group in gap_audit["groups"]:
        for day in dates:
            if group["first"] <= day <= group["last"]:
                code = group["code"]
                if code in gaps[day]:
                    raise ValueError("overlapping archived gap classifications")
                gaps[day][code] = group["reason"]
    for day in dates:
        active = listings_on(windows, day)
        ordinary[day] = {code: price for code, price in history[day].items() if code in active}
        if active.keys() - ordinary[day].keys() != gaps[day].keys():
            raise ValueError(f"archived gap classifications do not match the roster: {day}")
    replay = audit_adjusted_lows(ordinary, report["applied_events"], report["lookback"], listings=listings)
    for expected, actual in zip(report["sessions"], replay["sessions"], strict=True):
        if any(expected[key] != actual[key] for key in ("date", "eligible_codes", "adjusted_low_codes")):
            raise ValueError("archive and research report memberships differ")
    return dict(history=ordinary, listing_intervals=listings, applied_events=report["applied_events"],
                gap_reasons=gaps, lookback=report["lookback"], retention_sessions=retention,
                score_eligible=False)


def advance(checkpoint_raw, plan, read, *, allow_correction=False):
    if digest(checkpoint_raw) != plan["checkpoint_sha256"]:
        raise ValueError("checkpoint hash mismatch")
    checkpoint = json.loads(checkpoint_raw)
    history = checkpoint["history"]
    dates = sorted(history)
    lookback = checkpoint["lookback"]
    mode = plan["mode"]
    day = plan["session"]
    asof = iso(plan["as_of"])
    target = iso(day)
    last = iso(dates[-1])
    if plan["origin"] not in ("twse", "synthetic"):
        raise ValueError("unsupported update origin")
    if mode == "correction":
        if not allow_correction or day not in history or target > asof or not plan.get("revision_note", "").strip():
            raise ValueError("correction needs explicit approval, archived date and audit note")
        calendar_start = target
        calendar_end = target
    elif mode == "append":
        calendar_start = last + timedelta(days=1)
        calendar_end = asof
        if calendar_start > calendar_end:
            raise ValueError("no new calendar date to review")
    else:
        raise ValueError("unknown research update mode")
    sources = plan["sources"]
    calendar = load_evidence("calendar", sources["calendar"], read)
    expected_dates = [(calendar_start + timedelta(days=i)).isoformat()
                      for i in range((calendar_end - calendar_start).days + 1)]
    if [row["date"] for row in calendar] != expected_dates or any(
            row["state"] not in ("open", "closed") or not row["reason"].strip() for row in calendar):
        raise ValueError("calendar evidence must explicitly cover every elapsed date")
    opened = [row["date"] for row in calendar if row["state"] == "open"]
    if not opened and mode == "append":
        if day not in expected_dates:
            raise ValueError("closed session must be within reviewed calendar dates")
        return dict(status="closed", reviewed_through=asof.isoformat(), calendar=calendar,
                    sources={"calendar": sources["calendar"]}, score_eligible=False)
    if opened != [day]:
        raise ValueError("exactly one documented open session is required per update")
    if set(sources) != {"calendar", "quotes", "listings", "actions", "gaps"}:
        raise ValueError("open session requires all five source files")
    if plan["origin"] == "twse" and sources["quotes"]["source_url"] != QUOTE_URL + day.replace("-", ""):
        raise ValueError("official quote evidence requires the dated TWSE report URL")
    data = {kind: load_evidence(kind, sources[kind], read)
            for kind in ("quotes", "listings", "actions", "gaps")}
    for kind in ("listings", "actions", "gaps"):
        if data[kind]["date"] != day:
            raise ValueError(f"stale incremental source: {kind}")
    listings = data["listings"]["intervals"]
    before = listing_windows(checkpoint["listing_intervals"])
    after = listing_windows(listings)
    for old_day in dates:
        if mode == "correction" and old_day == day:
            continue
        old_members, new_members = listings_on(before, old_day), listings_on(after, old_day)
        if {c: row[0] for c, row in old_members.items()} != {c: row[0] for c, row in new_members.items()}:
            raise ValueError(f"retrospective listing change requires full rebuild: {old_day}")
    active = set(listings_on(after, day))
    raw_prices = parse_closes(data["quotes"], day)
    exclusions = data["listings"]["excluded_codes"]
    if len(set(exclusions)) != len(exclusions) or raw_prices.keys() - active != set(exclusions):
        raise ValueError("dated quote codes lack an explicit ordinary-share scope decision")
    prices = {code: raw_prices[code] for code in sorted(active & raw_prices.keys())
              if raw_prices[code] is not None}
    if not prices:
        raise ValueError("no eligible official quote rows for session")
    gap_reasons = data["gaps"]["reasons"]
    if active - prices.keys() != gap_reasons.keys() or any(
            reason not in REASONS - {"unconfirmed", "source_missing"} for reason in gap_reasons.values()):
        raise ValueError("missing-price evidence is incomplete or inconsistent")
    actions = data["actions"]
    if actions.get("coverage_reviewed") is not True or any(
            e["ex_date"] != day or e["code"] not in active for e in actions["events"]):
        raise ValueError("session action evidence is incomplete")
    history[day] = prices
    ordered = sorted(history)
    retention = checkpoint["retention_sessions"]
    if not 1 <= lookback < retention:
        raise ValueError("retention must include current and full prior window")
    retained = ordered[-retention:]
    history = {d: history[d] for d in retained}
    combined = [e for e in checkpoint["applied_events"] if e["ex_date"] != day] + actions["events"]
    events = [e for e in combined if e["ex_date"] in history and any(
        e["code"] in history[d] for d in retained if d < e["ex_date"])]
    if any(e not in events for e in actions["events"]):
        raise ValueError("new action requires a retained prior close")
    report = audit_adjusted_lows(history, events, lookback, listings=listings)
    gaps = {**checkpoint.get("gap_reasons", {}), day: gap_reasons}
    evidence = {**checkpoint.get("session_evidence", {}), day: dict(
        mode=mode, origin=plan["origin"], sources=sources,
        checkpoint_sha256=plan["checkpoint_sha256"], revision_note=plan.get("revision_note"))}
    state = dict(history=history, listing_intervals=listings, applied_events=events,
                 gap_reasons={d: gaps[d] for d in retained if d in gaps},
                 session_evidence={d: evidence[d] for d in retained if d in evidence},
                 lookback=lookback, retention_sessions=retention, score_eligible=False)
    if "seed_input_sha256" in checkpoint:
        state["seed_input_sha256"] = checkpoint["seed_input_sha256"]
    return dict(status="research_replay", origin=plan["origin"], checkpoint=state,
                report=report, score_eligible=False)


def fetch_quote(day):
    url = QUOTE_URL + iso(day).strftime("%Y%m%d")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=25) as response:
        raw = response.read()
    parse_closes(json.loads(raw), day)
    return raw


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch-quote")
    fetch.add_argument("session")
    fetch.add_argument("destination", type=Path)
    initialize = commands.add_parser("seed")
    for arg in ("history", "report", "gap_audit"):
        initialize.add_argument(arg, type=Path)
    update = commands.add_parser("replay")
    for arg in ("checkpoint", "plan", "directory"):
        update.add_argument(arg, type=Path)
    update.add_argument("--allow-correction", action="store_true")
    args = parser.parse_args()
    if args.command == "fetch-quote":
        raw = fetch_quote(args.session)
        with args.destination.open("xb") as destination:
            destination.write(raw)
        print(json.dumps(dict(source_url=QUOTE_URL + args.session.replace("-", ""), sha256=digest(raw))))
    elif args.command == "seed":
        inputs = (args.history, args.report, args.gap_audit)
        result = seed(*(json.loads(path.read_bytes()) for path in inputs))
        result["seed_input_sha256"] = {path.name: digest(path.read_bytes()) for path in inputs}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(advance(args.checkpoint.read_bytes(), json.loads(args.plan.read_bytes()),
                                 lambda kind: (args.directory / f"{kind}.json").read_bytes(),
                                 allow_correction=args.allow_correction), ensure_ascii=False, indent=2))
