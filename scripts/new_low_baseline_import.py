"""Normalize a licensed external CSV export for the research comparator."""
import argparse
import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path

from scripts.corporate_action_audit import positive
from scripts.new_low_listing import listing_windows

QUOTE_COLUMNS = ["date", "code", "adjusted_close"]
CALENDAR_COLUMNS = ["date"]
LISTING_COLUMNS = ["code", "listed_from", "delisted_on"]


def rows(raw, fields):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != fields:
        raise ValueError("unexpected CSV columns: " + ", ".join(fields))
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("wrong CSV row width")
        yield row


def security_code(code):
    return len(code) == 4 and code.isascii() and code.isdigit() and not code.startswith("0")


def normalize(metadata, quotes, calendar, listings=None):
    for field in ("provider", "source_url", "adjustment_method", "data_origin", "usage_basis"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"missing export provenance: {field}")
    if not metadata["source_url"].startswith("https://"):
        raise ValueError("export source URL must use HTTPS")
    if metadata["data_origin"] != "provider_adjusted_close":
        raise ValueError("export must contain provider-adjusted closes")
    dates = [row["date"] for row in rows(calendar, CALENDAR_COLUMNS)]
    if (not dates or dates != sorted(set(dates))
            or any(date.fromisoformat(day).isoformat() != day for day in dates)):
        raise ValueError("calendar must contain ordered unique ISO sessions")
    prices = {day: {} for day in dates}
    for row in rows(quotes, QUOTE_COLUMNS):
        day, code, price = row["date"], row["code"], row["adjusted_close"]
        if day not in prices or not security_code(code):
            raise ValueError("quote outside market calendar or ordinary stock code format")
        if code in prices[day]:
            raise ValueError(f"duplicate adjusted close: {day} {code}")
        prices[day][code] = str(positive(price))
    if not any(prices.values()):
        raise ValueError("export contains no adjusted closes")
    result = {field: metadata[field] for field in (
        "provider", "source_url", "adjustment_method", "data_origin", "usage_basis")}
    result["market_dates"] = dates
    result["adjusted_closes"] = prices
    result["sha256"] = {"quotes": hashlib.sha256(quotes).hexdigest(),
                        "calendar": hashlib.sha256(calendar).hexdigest()}
    if listings is not None:
        intervals = [dict(row, delisted_on=row["delisted_on"] or None)
                     for row in rows(listings, LISTING_COLUMNS)]
        if not intervals:
            raise ValueError("listing export contains no intervals")
        listing_windows(intervals)
        result["listings"] = intervals
        result["sha256"]["listings"] = hashlib.sha256(listings).hexdigest()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("quotes", type=Path)
    parser.add_argument("calendar", type=Path)
    parser.add_argument("--listings", type=Path)
    args = parser.parse_args()
    data = normalize(json.loads(args.metadata.read_text()), args.quotes.read_bytes(),
                     args.calendar.read_bytes(), args.listings.read_bytes() if args.listings else None)
    print(json.dumps(data, ensure_ascii=False, indent=2))
