"""Parse TWSE TWT49U result rows into *candidate* corporate-action events.

This parser deliberately does NOT mark records verified. Source retrieval,
completeness (including capital reductions), and previous-close reconciliation
must be checked independently before an event can be approved.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS = ("資料日期", "股票代號", "除權息前收盤價", "除權息參考價", "權/息")


def roc_date(value):
    s = str(value).strip().replace("年", "/").replace("月", "/").replace("日", "")
    parts = s.split("/")
    if len(parts) != 3:
        raise ValueError("invalid ROC date")
    try:
        year, month, day = (int(p) for p in parts)
        return date(year + 1911, month, day).isoformat()
    except ValueError as exc:
        raise ValueError("invalid ROC date") from exc


def parse_result_rows(rows, source_url):
    """Accept dict rows using the published Chinese column labels."""
    if not str(source_url).startswith("https://www.twse.com.tw/"):
        raise ValueError("TWSE official source required")
    result = []
    for row in rows:
        if not isinstance(row, dict) or any(k not in row for k in FIELDS):
            raise ValueError("unexpected TWT49U schema")
        code = str(row["股票代號"]).strip()
        if len(code) != 4 or not code.isdigit() or code[0] == "0":
            continue  # Exclude ETF and non-four-digit common-stock codes.
        try:
            prior = Decimal(str(row["除權息前收盤價"]).replace(",", ""))
            reference = Decimal(str(row["除權息參考價"]).replace(",", ""))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("invalid official price") from exc
        if not all(v.is_finite() and v > 0 for v in (prior, reference)):
            raise ValueError("invalid official price")
        event_type = str(row["權/息"]).strip()
        if event_type not in ("權", "息", "權息", "權/息"):
            raise ValueError("unrecognized corporate action type")
        result.append({
            "code": code,
            "ex_date": roc_date(row["資料日期"]),
            "prior_close": str(prior),
            "reference_price": str(reference),
            "event_type": event_type,
            "source_url": source_url,
            "verified": False,
            "verification_note": "candidate only; historical completeness and price basis not audited",
        })
    return result
