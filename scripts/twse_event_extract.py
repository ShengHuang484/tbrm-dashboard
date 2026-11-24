"""Extract TWSE TWT49U rows from archived JSON with explicit schema checks.

Unrecognized columns fail closed. Parsed records remain unverified candidates.
"""
from scripts.twse_corporate_action_parser import parse_result_rows

ALIASES = {
    "date": ("除權息日期", "資料日期"),
    "code": ("股票代號", "代號"),
    "prior": ("除權息前收盤價",),
    "reference": ("除權息參考價",),
    "kind": ("權/息",),
}


def _column(fields, names):
    matches = [name for name in names if name in fields]
    if len(matches) != 1:
        raise ValueError("required TWSE column missing or ambiguous: " + "/".join(names))
    return fields.index(matches[0])


def extract_candidates(payload, source_url):
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        raise ValueError("TWSE did not return OK")
    tables = payload.get("tables")
    if tables is None:
        tables = [payload]
    if not isinstance(tables, list) or not tables:
        raise ValueError("missing TWSE tables")
    candidates = []
    for table in tables:
        if not isinstance(table, dict):
            raise ValueError("invalid TWSE table")
        fields, data = table.get("fields"), table.get("data")
        if not isinstance(fields, list) or not isinstance(data, list):
            raise ValueError("invalid TWSE table shape")
        if not data:
            continue
        positions = {key: _column(fields, names) for key, names in ALIASES.items()}
        normalized = []
        for values in data:
            if not isinstance(values, list) or len(values) != len(fields):
                raise ValueError("TWSE row length mismatch")
            normalized.append({
                "除權息日期": values[positions["date"]],
                "股票代號": values[positions["code"]],
                "除權息前收盤價": values[positions["prior"]],
                "除權息參考價": values[positions["reference"]],
                "權/息": values[positions["kind"]],
            })
        candidates.extend(parse_result_rows(normalized, source_url))
    return candidates
