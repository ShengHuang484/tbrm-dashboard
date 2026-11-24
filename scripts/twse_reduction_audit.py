"""Archive and inventory candidates from the TWSE capital-reduction result report."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.twse_corporate_action_parser import roc_date

BASE = "https://www.twse.com.tw/exchangeReport/TWTAUU"
FIELDS = ("恢復買賣日期", "股票代號", "停止買賣前收盤價格",
          "恢復買賣參考價", "除權參考價", "減資原因")


def inventory(payload, start, end):
    fields = payload.get("fields")
    rows = payload.get("data")
    if (payload.get("stat") != "OK" or not isinstance(fields, list)
            or not isinstance(rows, list) or not all(fields.count(f) == 1 for f in FIELDS)):
        raise ValueError("unexpected TWTAUU response")
    # The report title identifies the actual queried period and detects date
    # parameters silently ignored by the endpoint.
    title = payload.get("title", "")
    for bound in (start, end):
        day = date.fromisoformat(bound)
        if f"{day.year - 1911}年{day.month:02d}月{day.day:02d}日" not in title:
            raise ValueError("TWTAUU title does not cover the requested bounds")
    candidates = []
    identities = set()
    for values in rows:
        if not isinstance(values, list) or len(values) != len(fields):
            raise ValueError("malformed TWTAUU row")
        row = dict(zip(fields, values))
        effective = roc_date(row["恢復買賣日期"])
        if not start <= effective <= end:
            raise ValueError("TWTAUU event outside query period")
        code = str(row["股票代號"]).strip()
        if (code, effective) in identities:
            raise ValueError("duplicate TWTAUU event")
        identities.add((code, effective))
        candidates.append({
            "code": code,
            "effective_date": effective,
            "pre_halt_close": row["停止買賣前收盤價格"],
            "resumption_reference": row["恢復買賣參考價"],
            "rights_reference": row["除權參考價"],
            "reason": row["減資原因"],
            "verified": False,
        })
    return candidates


def archive(history, output):
    start, *_, end = sorted(history)
    url = BASE + "?" + urlencode({
        "response": "json",
        "startDate": start.replace("-", ""),
        "endDate": end.replace("-", ""),
    })
    output.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "TBRM-research/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=25) as response:
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("TWTAUU response exceeds limit")
    (output / "raw.json").write_bytes(raw)
    candidates = inventory(json.loads(raw.decode("utf-8-sig")), start, end)
    report = {
        "source": url, "start": start, "end": end,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "research_only": True, "score_eligible": False,
        "corporate_action_completeness_verified": False,
        "candidates": candidates,
    }
    (output / "inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = archive(json.loads(args.history.read_text(encoding="utf-8")), args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
