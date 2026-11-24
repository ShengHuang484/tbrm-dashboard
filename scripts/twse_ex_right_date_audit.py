"""Check the two candidate sessions against archived TWSE daily reports."""
import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import Request, urlopen

from scripts.twse_corporate_action_parser import roc_date
from scripts.twse_quote_gap_crosscheck import plain

BASE = "https://www.twse.com.tw/exchangeReport/"


def tables(payload):
    if payload.get("stat") != "OK":
        raise ValueError("TWSE response did not confirm success")
    yield from payload.get("tables", [])
    for suffix in ("", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        fields, data = payload.get("fields" + suffix), payload.get("data" + suffix)
        if isinstance(fields, list) and isinstance(data, list):
            yield {"fields": fields, "data": data}


def select_rows(payload, code_field, codes, required):
    matches = []
    for table in tables(payload):
        fields = [plain(value).replace(" ", "") for value in table.get("fields", [])]
        if not {code_field, *required} <= set(fields):
            continue
        for values in table["data"]:
            if len(values) != len(fields):
                raise ValueError("invalid TWSE row width")
            row = dict(zip(fields, map(plain, values)))
            if row[code_field] in codes:
                matches.append(row)
    return matches


def implied_auction_base(quote):
    """Compute a diagnostic price basis from a signed, decimal change."""
    if not quote:
        return None
    sign = quote["漲跌(+/-)"]
    try:
        close, change = (Decimal(quote[field].replace(",", ""))
                         for field in ("收盤價", "漲跌價差"))
    except InvalidOperation:
        return None
    if not close.is_finite() or not change.is_finite() or close <= 0 or change < 0:
        return None
    if sign == "+" or (sign == "" and change == 0):
        base = close - change
    elif sign == "-":
        base = close + change
    else:
        return None
    return base if base > 0 else None


def evaluate(day, cases, quotes, ex_rights):
    if str(quotes.get("date", "")).replace("/", "") != day.replace("-", ""):
        raise ValueError("daily quotes date mismatch")
    key = day.replace("-", "")
    if (ex_rights.get("strDate"), ex_rights.get("endDate")) != (key, key):
        raise ValueError("daily ex-rights query bounds mismatch")
    codes = {case["code"] for case in cases}
    quote_rows = select_rows(quotes, "證券代號", codes, {"收盤價", "漲跌(+/-)", "漲跌價差"})
    result_rows = select_rows(ex_rights, "股票代號", codes,
                              {"資料日期", "除權息前收盤價", "除權息參考價", "開盤競價基準"})
    if any(roc_date(row["資料日期"]) != day for row in result_rows):
        raise ValueError("ex-rights row date mismatch")
    if len({r["證券代號"] for r in quote_rows}) != len(quote_rows):
        raise ValueError("duplicate daily quote")
    if len({r["股票代號"] for r in result_rows}) != len(result_rows):
        raise ValueError("duplicate daily event")
    quotes_by_code = {row["證券代號"]: row for row in quote_rows}
    results_by_code = {row["股票代號"]: row for row in result_rows}
    report = []
    for case in cases:
        code = case["code"]
        quote = quotes_by_code.get(code)
        base = implied_auction_base(quote)
        match = base is not None and base == Decimal(case["auction_base"])
        report.append(dict(
            case, quote=quote, dated_event=results_by_code.get(code),
            implied_auction_base=str(base) if base is not None else None,
            official_trading_basis_matches=bool(match and base != Decimal(case["prior_close"])),
            score_eligible=False,
        ))
    return report


def capture(url, path):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(request, timeout=25) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("TWSE response exceeds size limit")
    path.write_bytes(raw)
    return json.loads(raw), {"url": url, "sha256": hashlib.sha256(raw).hexdigest()}


def audit(cases, output):
    output.mkdir(parents=True, exist_ok=True)
    reports, sources = [], {}
    for day in sorted({case["candidate_date"] for case in cases}):
        key = day.replace("-", "")
        for label, query in {
            "quotes": f"MI_INDEX?response=json&date={key}&type=ALLBUT0999",
            "ex_rights": f"TWT49U?response=json&startDate={key}&endDate={key}",
        }.items():
            filename = f"{day}-{label}.json"
            _, sources[filename] = capture(BASE + query, output / filename)
        reports.extend(evaluate(
            day, [case for case in cases if case["candidate_date"] == day],
            *(json.loads((output / f"{day}-{label}.json").read_bytes())
              for label in ("quotes", "ex_rights")),
        ))
    return {"cases": reports, "sources": sources, "score_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = audit(json.loads(args.cases.read_text()), args.output)
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
