"""Replay partial TWSE session evidence without publishing a research low count."""
import argparse
import json
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.historical_roster_check import check as check_roster
from scripts.new_low_incremental import QUOTE_URL, advance, digest, parse_closes
from scripts.new_low_baseline_import import security_code
from scripts.new_low_listing import listing_windows, listings_on
from scripts.twse_corporate_action_parser import roc_date
from scripts.twse_stock_day_gaps import capture, replay_evidence, source_url

ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
TIB_ISIN_URL = ("https://isin.twse.com.tw/isin/class_main.jsp?"
                "owncode=&stockname=&isincode=&market=C&issuetype=C&industry_code=&Page=1&chklike=Y")
TDR_ISIN_URL = "https://isin.twse.com.tw/isin/class_main.jsp?chklike=Y&issuetype=J&market=1"


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def ordinary_isin_prefix(raw, day):
    # This boundary isolates the complete general-board stock section from the
    # much larger warrant catalogue. Other listing boards are outside the section.
    stop = "上市認購(售)權證".encode("cp950")
    end = raw.find(stop)
    if end < 0:
        raise ValueError("ISIN prefix does not cover the whole general-board section")
    text = raw[:end].decode("cp950")
    matches = re.findall(r"最近更新日期:\s*([0-9]{4}/[0-9]{2}/[0-9]{2})", text)
    if matches != [day.replace("-", "/")]:
        raise ValueError("ISIN snapshot update date does not match the research session")
    parser = Rows()
    parser.feed(text)
    starts = [i for i, fields in enumerate(parser.rows) if fields == ["股票"]]
    if len(starts) != 1:
        raise ValueError("cannot identify the ordinary stock section")
    identities = {}
    ids = set()
    for fields in parser.rows[starts[0] + 1:]:
        if len(fields) != 7:
            raise ValueError("unexpected row in the ordinary stock section")
        code = fields[0].split()[0]
        isin = fields[1]
        listed = date.fromisoformat(fields[2].replace("/", "-"))
        if (not security_code(code) or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin)
                or fields[3] != "上市" or not fields[5].startswith("ES")
                or code in identities or isin in ids or listed.isoformat() > day):
            raise ValueError(f"invalid general-board identity: {code}")
        identities[code] = dict(security_id=isin, listed_from=listed.isoformat(), cfi=fields[5])
        ids.add(isin)
    if not identities:
        raise ValueError("empty ordinary stock section")
    return identities


def scoped_isins(raw, market, kind, cfi_prefix):
    parser = Rows()
    parser.feed(raw.decode("cp950"))
    identifiers = {}
    header = ["頁面編號", "國際證券編碼", "有價證券代號", "有價證券名稱", "市場別", "有價證券別",
              "產業別", "公開發行/上市(櫃)/發行日", "CFICode", "備註"]
    if not parser.rows or parser.rows[0] != header:
        raise ValueError("unexpected scoped ISIN report schema")
    for number, row in enumerate(parser.rows[1:], start=1):
        index, isin, code, _, actual_market, actual_kind, _, listed_on, cfi, _ = row
        if (index != str(number) or (market, kind) != (actual_market, actual_kind)
                or not cfi.startswith(cfi_prefix) or not re.fullmatch(r"[1-9][0-9]{3,5}", code)
                or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin)
                or code in identifiers):
            raise ValueError(f"invalid scoped ISIN row for {code}")
        identifiers[code] = dict(security_id=isin, listed_from=date.fromisoformat(
            listed_on.replace("/", "-")).isoformat())
    if not identifiers or len({row["security_id"] for row in identifiers.values()}) != len(identifiers):
        raise ValueError("empty or duplicated scoped ISIN identities")
    return identifiers


def check_full_isin(raw, day, general, innovation, tdr):
    """Compare a complete published page with the separately scoped reports."""
    text = raw.decode("cp950")
    if not re.search(r"</table>\s*<font[^>]*><center>掛牌日以正式公告為準</center></font>\s*$",
                     text, re.IGNORECASE):
        raise ValueError("ISIN full response is incomplete")
    if ordinary_isin_prefix(raw, day) != general:
        raise ValueError("full and prefix general-board identities disagree")
    sections = list(re.finditer(
        r"<tr\b[^>]*>\s*<td\b[^>]*colspan\s*=\s*7[^>]*>\s*<b>\s*([^<]+)", text, re.IGNORECASE))
    for label, expected in (("創新板", innovation), ("臺灣存託憑證(TDR)", tdr)):
        indices = [i for i, section in enumerate(sections) if section[1].strip() == label]
        if len(indices) != 1 or indices[0] >= len(sections) - 1:
            raise ValueError(f"full ISIN section boundary missing: {label}")
        index, = indices
        parser = Rows()
        parser.feed(text[sections[index].start():sections[index + 1].start()])
        seen = {}
        for row in parser.rows[1:]:
            name, isin, listed_on, _, _, _, _ = row
            code = name.split()[0]
            if code in seen:
                raise ValueError(f"duplicate full ISIN code: {code}")
            seen[code] = dict(security_id=isin, listed_from=date.fromisoformat(
                listed_on.replace("/", "-")).isoformat())
        if seen != expected:
            raise ValueError(f"full and scoped ISIN identities disagree: {label}")
    return dict(general_board=len(general), innovation_board=len(innovation), tdr_rows=len(tdr))


ACTION_WINDOWS = {
    "ex_window": ("https://www.twse.com.tw/rwd/zh/exRight/TWT49U", "資料日期"),
    "reduction_window": ("https://www.twse.com.tw/exchangeReport/TWTAUU", "恢復買賣日期"),
}


def compare_action_windows(day, inputs, reduction_rows):
    available = ACTION_WINDOWS.keys() & inputs.keys()
    if not available:
        return {}, {}
    if available != ACTION_WINDOWS.keys():
        raise ValueError("action window review requires both TWSE reports")

    summaries, sources = {}, {}
    for key, (url, date_column) in ACTION_WINDOWS.items():
        payload = json.loads(inputs[key])
        start, end = payload.get("strDate", ""), payload.get("endDate", "")
        compact = day.replace("-", "")
        if (payload.get("stat") != "OK" or not re.fullmatch(r"[0-9]{8}", start)
                or not re.fullmatch(r"[0-9]{8}", end) or not start < compact < end):
            raise ValueError(f"{key} does not cover both sides of the session")
        fields = payload["fields"]
        if len(set(fields)) != len(fields) or not {date_column, "股票代號"} <= set(fields):
            raise ValueError(f"{key} has invalid date or security columns")
        by_date = {}
        target_rows = []
        for raw in payload["data"]:
            row = dict(zip(fields, raw, strict=True))
            effective = roc_date(row[date_column])
            if not start <= effective.replace("-", "") <= end:
                raise ValueError(f"{key} contains a row outside its declared dates")
            by_date.setdefault(effective, []).append(row["股票代號"])
            if effective == day:
                target_rows.append(row)
        expected_rows = [] if key == "ex_window" else reduction_rows
        if ([sorted(row.items()) for row in target_rows] !=
                [sorted(row.items()) for row in expected_rows]):
            raise ValueError(f"{key} disagrees with the target-day response")
        summaries[key] = dict(start=start, end=end, observed_codes_by_date=by_date,
                              target_rows=len(target_rows), coverage_reviewed=False)
        sources[key] = f"{url}?response=json&startDate={start}&endDate={end}"
    return summaries, sources


def evidence_report(day, checkpoint, inputs, *, identity_retrieved_on=None, include_roster_reference=False):
    historical = json.loads(checkpoint)
    history = historical["history"]
    previous = max(history)
    day_compact = day.replace("-", "")
    quotes = parse_closes(json.loads(inputs["quotes"]), day)
    roster = ordinary_isin_prefix(inputs["isin_prefix"], day)
    tib_payload = json.loads(inputs["tib"])
    tib_tables = [table for table in tib_payload.get("tables", [])
                  if "每日收盤行情(創新板股票)" in table.get("title", "")]
    if len(tib_tables) != 1:
        raise ValueError("expected an official Innovation Board close table")
    tib = parse_closes(dict(stat=tib_payload.get("stat"), date=tib_payload.get("date"),
                            tables=tib_tables), day)
    if roster.keys() & tib.keys() or any(code not in quotes or quotes[code] != value for code, value in tib.items()):
        raise ValueError("Innovation Board and official quote scopes disagree")
    calendar = json.loads(inputs["calendar"])
    dates = [roc_date(row[0]) for row in calendar["data"]]
    if (calendar.get("stat") != "OK" or dates != sorted(set(dates)) or
            any(d[:7] != day[:7] for d in dates) or
            [d for d in dates if previous < d <= day] != [day]):
        raise ValueError("official monthly report cannot verify the open-session boundary")
    if previous[:7] != day[:7] or previous not in dates:
        raise ValueError("session probe requires checkpoint month and date in the official report")
    reduction = json.loads(inputs["reduction"])
    fields = reduction["fields"]
    if (reduction.get("stat") != "OK" or len(set(fields)) != len(fields)
            or reduction.get("strDate") != day_compact or reduction.get("endDate") != day_compact):
        raise ValueError("invalid reduction report")
    events = []
    for raw in reduction["data"]:
        row = dict(zip(fields, raw, strict=True))
        code = row["股票代號"]
        old_date = max(d for d in history if code in history[d])
        match = positive(history[old_date][code]) == positive(row["停止買賣前收盤價格"].replace(",", ""))
        if roc_date(row["恢復買賣日期"]) != day or not match or not quotes.get(code):
            raise ValueError(f"reduction cannot reconcile to archived and current closes: {code}")
        events.append(dict(code=code, old_session=old_date, old_close=row["停止買賣前收盤價格"],
                           exchange_reference=row["恢復買賣參考價"], official_close=quotes[code]))
    ex_right = json.loads(inputs["ex_right"])
    if not ("沒有符合條件" in ex_right.get("stat", "") and not ex_right.get("data")):
        raise ValueError("ex-right response requires event-by-event review")
    gap_evidence = capture("1538", day[:7], [day], inputs["stock_1538"])
    gap = dict(replay_evidence([gap_evidence]))
    if "1538" not in quotes or quotes["1538"] is not None or gap["1538", day] not in {
            "activity_without_close", "zero_reported_activity"}:
        raise ValueError("1538 gap requires a reconciled quote and activity record")
    next_day = date.fromisoformat(previous) + timedelta(days=1)
    decisions = []
    while next_day.isoformat() <= day:
        session = next_day.isoformat()
        state = "open" if session in dates else "closed"
        decisions.append(dict(date=session, state=state, reason="official monthly market trading report"))
        next_day += timedelta(days=1)
    calendar_url = "https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date=" + day_compact[:6] + "01"
    normalized_calendar = json.dumps(decisions).encode()
    plan = dict(checkpoint_sha256=digest(checkpoint), mode="append", origin="twse", session=day,
                as_of=day, sources={
                    "calendar": dict(source_url=calendar_url, sha256=digest(normalized_calendar)),
                    "quotes": dict(source_url=QUOTE_URL + day_compact, sha256=digest(inputs["quotes"]))})
    sources = {
        "quotes": QUOTE_URL + day_compact,
        "calendar": calendar_url,
        "isin_prefix": ISIN_URL,
        "tib": QUOTE_URL.replace("ALLBUT0999", "TIB") + day_compact,
        "reduction": f"https://www.twse.com.tw/exchangeReport/TWTAUU?response=json&startDate={day_compact}&endDate={day_compact}",
        "ex_right": f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json&startDate={day_compact}&endDate={day_compact}",
        "stock_1538": source_url("1538", day[:7]),
    }
    action_windows, action_sources = compare_action_windows(
        day, inputs, [dict(zip(fields, raw, strict=True)) for raw in reduction["data"]])
    sources.update(action_sources)
    normalized = {"calendar": normalized_calendar, "quotes": inputs["quotes"]}
    scoped_evidence = {}
    roster_reference = None
    blockers = ["complete dated ordinary-share roster with Innovation Board security identifiers and scope exclusions",
                "complete reviewed corporate-action coverage", "gap status reconciled against the complete roster"]
    expected_error = "open session requires all five source files"
    if {"tib_isin", "tdr_isin"} & inputs.keys():
        if identity_retrieved_on != day or not {"tib_isin", "tdr_isin"} <= inputs.keys():
            raise ValueError("scoped ISIN evidence requires both reports and same-day capture")
        tib_ids = scoped_isins(inputs["tib_isin"], "上市臺灣創新板", "創新板", "ES")
        tdr_ids = scoped_isins(inputs["tdr_isin"], "上市", "臺灣存託憑證(TDR)", "ED")
        exclusions = quotes.keys() - roster.keys() - tib.keys()
        ids = roster | tib_ids
        windows = listing_windows(historical["listing_intervals"])
        active = listings_on(windows, day)
        if (tib_ids.keys() != tib.keys() or len({r["security_id"] for r in ids.values()}) != len(ids)
                or exclusions != {code for code in tdr_ids if security_code(code)}
                or ids.keys() != active.keys() or any(row["listed_from"] > day for row in ids.values())):
            raise ValueError("scoped ISIN evidence and the checkpoint's session membership disagree")
        reasons = {"1538": gap["1538", day]}
        if {code for code in ids if not quotes.get(code)} != reasons.keys():
            raise ValueError("complete ordinary scope has unresolved missing closes")
        roster_csv = ("date,code,security_id\n" + "".join(
            f"{day},{code},{ids[code]['security_id']}\n" for code in sorted(ids))).encode()
        membership = check_roster(dict(market_dates=[day], listing_intervals=historical["listing_intervals"]),
                                  dict(origin="twse", retrieved_on=identity_retrieved_on, covered_dates=[day],
                                       source_url=ISIN_URL, sha256=digest(roster_csv)), roster_csv)
        scoped_evidence = dict(
            identity_retrieved_on=identity_retrieved_on, same_source_ordinary_member_count=len(ids),
            roster_check=dict(delivery_coverage_status=membership["delivery_coverage_status"],
                              sessions_with_membership_differences=membership["sessions_with_membership_differences"],
                              normalized_roster_sha256=digest(roster_csv)),
            innovation_board_isins={code: row["security_id"] for code, row in tib_ids.items()},
            tdr_exclusions={code: tdr_ids[code]["security_id"] for code in sorted(exclusions)},
            listing_start_differences=[dict(code=code, archived=active[code][0], isin=ids[code]["listed_from"])
                                       for code in sorted(ids) if active[code][0] != ids[code]["listed_from"]],
            independent_membership_verified=False)
        normalized.update({
            "listings": json.dumps(dict(date=day, intervals=historical["listing_intervals"],
                                        excluded_codes=sorted(exclusions))).encode(),
            "gaps": json.dumps(dict(date=day, reasons=reasons)).encode(),
            "actions": json.dumps(dict(date=day, coverage_reviewed=False, events=[])).encode(),
        })
        for kind, url in (("listings", ISIN_URL), ("gaps", sources["stock_1538"]), ("actions", sources["reduction"])):
            plan["sources"][kind] = dict(source_url=url, sha256=digest(normalized[kind]))
        sources.update(tib_isin=TIB_ISIN_URL, tdr_isin=TDR_ISIN_URL)
        if "isin_full" in inputs:
            scoped_evidence["full_isin_crosscheck"] = check_full_isin(
                inputs["isin_full"], day, roster, tib_ids, tdr_ids)
            sources["isin_full"] = ISIN_URL
        if include_roster_reference:
            roster_reference = dict(
                market_dates=[day],
                listing_intervals=[
                    dict(code=code, listed_from=active[code][0], delisted_on=active[code][1],
                         security_id=ids[code]["security_id"])
                    for code in sorted(ids)],
                reference_scope="same_source_twse_one_session_membership_only",
                normalized_roster_sha256=digest(roster_csv),
            )
        expected_error = "session action evidence is incomplete"
        blockers = ["complete reviewed corporate-action coverage"]
        if scoped_evidence["listing_start_differences"]:
            blockers.append("resolve the observed listing-start differences before updating historical intervals")
    try:
        advance(checkpoint, plan, normalized.__getitem__)
    except ValueError as exc:
        if str(exc) != expected_error:
            raise
        blocked = str(exc)
    else:
        raise ValueError("partial source probe unexpectedly advanced checkpoint")
    if include_roster_reference and roster_reference is None:
        raise ValueError("roster reference requires both scoped ISIN reports")
    return dict(status="BLOCKED", session=day, calendar=decisions,
                checkpoint_sha256=digest(checkpoint), seed_input_sha256=historical["seed_input_sha256"],
                official_quote_codes=len(quotes), valid_close_codes=sum(v is not None for v in quotes.values()),
                identified_general_board_codes=len(roster), identified_missing_quote_codes=sorted(
                    code for code in roster if not quotes.get(code)),
                innovation_board_trade_table_codes=sorted(tib),
                quoted_codes_outside_observed_boards=sorted(quotes.keys() - roster.keys() - tib.keys()),
                reduction_observations=events, ex_right_response=ex_right["stat"],
                action_window_observations=action_windows,
                confirmed_gap_reasons={"1538": gap["1538", day]}, gap_evidence=gap_evidence, replay_error=blocked,
                blocked_inputs=blockers, scoped_identity_evidence=scoped_evidence,
                replay_input_sha256={key: digest(value) for key, value in normalized.items()},
                sources={k: dict(url=sources[k], sha256=digest(value), bytes=len(value),
                                body_scope="downloaded_prefix" if k == "isin_prefix" else "full")
                         for k, value in inputs.items()},
                score_eligible=False,
                **({"roster_reference": roster_reference} if include_roster_reference else {}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--identity-retrieved-on")
    parser.add_argument("--roster-reference-output", type=Path,
                        help="write a separate same-source benchmark for this session only")
    args = parser.parse_args()
    inputs = {key: (args.evidence / (key + ".raw")).read_bytes() for key in
              ("quotes", "calendar", "isin_prefix", "tib", "reduction", "ex_right", "stock_1538")}
    if args.identity_retrieved_on:
        inputs.update({key: (args.evidence / (key + ".raw")).read_bytes() for key in ("tib_isin", "tdr_isin")})
        full = args.evidence / "isin_full.raw"
        if full.exists():
            inputs["isin_full"] = full.read_bytes()
    for key in ACTION_WINDOWS:
        raw = args.evidence / (key + ".raw")
        if raw.exists():
            inputs[key] = raw.read_bytes()
    report = evidence_report(args.session, args.checkpoint.read_bytes(), inputs,
                             identity_retrieved_on=args.identity_retrieved_on,
                             include_roster_reference=args.roster_reference_output is not None)
    if args.roster_reference_output is not None:
        reference = report.pop("roster_reference")
        reference["sources"] = {key: report["sources"][key]
                                for key in ("isin_prefix", "tib_isin", "tdr_isin", "isin_full")
                                if key in report["sources"]}
        args.roster_reference_output.write_text(json.dumps(reference, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
