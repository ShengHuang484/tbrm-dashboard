"""Replay partial TWSE session evidence without publishing a research low count."""
import argparse
import json
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.new_low_incremental import QUOTE_URL, advance, digest, parse_closes
from scripts.new_low_baseline_import import security_code
from scripts.twse_corporate_action_parser import roc_date
from scripts.twse_stock_day_gaps import capture, replay_evidence, source_url

ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"


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


def evidence_report(day, checkpoint, inputs):
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
    try:
        advance(checkpoint, plan, {"calendar": normalized_calendar, "quotes": inputs["quotes"]}.__getitem__)
    except ValueError as exc:
        if str(exc) != "open session requires all five source files":
            raise
        blocked = str(exc)
    else:
        raise ValueError("partial source probe unexpectedly advanced checkpoint")
    sources = {
        "quotes": QUOTE_URL + day_compact,
        "calendar": calendar_url,
        "isin_prefix": ISIN_URL,
        "tib": QUOTE_URL.replace("ALLBUT0999", "TIB") + day_compact,
        "reduction": f"https://www.twse.com.tw/exchangeReport/TWTAUU?response=json&startDate={day_compact}&endDate={day_compact}",
        "ex_right": f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json&startDate={day_compact}&endDate={day_compact}",
        "stock_1538": source_url("1538", day[:7]),
    }
    return dict(status="BLOCKED", session=day, calendar=decisions,
                checkpoint_sha256=digest(checkpoint), seed_input_sha256=historical["seed_input_sha256"],
                official_quote_codes=len(quotes), valid_close_codes=sum(v is not None for v in quotes.values()),
                identified_general_board_codes=len(roster), identified_missing_quote_codes=sorted(
                    code for code in roster if not quotes.get(code)),
                innovation_board_trade_table_codes=sorted(tib),
                quoted_codes_outside_observed_boards=sorted(quotes.keys() - roster.keys() - tib.keys()),
                reduction_observations=events, ex_right_response=ex_right["stat"],
                confirmed_gap_reasons={"1538": gap["1538", day]}, gap_evidence=gap_evidence, replay_error=blocked,
                blocked_inputs=["complete dated ordinary-share roster with Innovation Board security identifiers and scope exclusions",
                                "complete reviewed corporate-action coverage",
                                "gap status reconciled against the complete roster"],
                sources={k: dict(url=sources[k], sha256=digest(value), bytes=len(value),
                                body_scope="downloaded_prefix" if k == "isin_prefix" else "full")
                         for k, value in inputs.items()},
                score_eligible=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    inputs = {key: (args.evidence / (key + ".raw")).read_bytes() for key in
              ("quotes", "calendar", "isin_prefix", "tib", "reduction", "ex_right", "stock_1538")}
    report = evidence_report(args.session, args.checkpoint.read_bytes(), inputs)
    print(json.dumps(report, ensure_ascii=False, indent=2))
