"""Validate three supplier samples without granting research or scoring approval."""

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from scripts.historical_roster_check import COLUMNS
from scripts.new_low_baseline_import import rows, security_code

FILES = ("lifecycle", "rights", "roster")
LIFECYCLE_COLUMNS = ["date", "code", "security_id", "status", "raw_close",
                     "adjusted_close", "successor_code", "exchange_ratio"]
RIGHTS_COLUMNS = ["date", "code", "raw_close", "adjusted_1340", "adjusted_1320"]
ISIN_PATTERN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
SESSION = "2026-11-23"
ANCHOR = "2026-11-20"
LIFECYCLE = {
    ("2026-08-19", "2867"): ("last_trade", "9.70"),
    ("2026-08-20", "2867"): ("suspended", ""),
    ("2026-09-01", "2867"): ("delisted", ""),
    ("2026-09-01", "2884"): ("successor_trading", "39.90"),
}
RIGHTS_CLOSES = {"2026-05-27": "9.98", "2026-06-10": "13.20",
                 "2026-06-11": "12.85", ANCHOR: "10.00"}


def price(value, places):
    if not re.fullmatch(rf"[0-9]+\.[0-9]{{{places},10}}", value) or Decimal(value) <= 0:
        raise ValueError(f"expected positive price with at least {places} decimals")
    return Decimal(value)


def verify_lifecycle(raw):
    observed = {}
    identities = {"2867": set(), "2884": set()}
    for row in rows(raw, LIFECYCLE_COLUMNS):
        key = row["date"], row["code"]
        if key in observed or key not in LIFECYCLE:
            raise ValueError(f"unexpected or duplicate lifecycle row: {key}")
        expected_status, close = LIFECYCLE[key]
        code = row["code"]
        if (row["status"] != expected_status or not ISIN_PATTERN.fullmatch(row["security_id"])
                or not row["security_id"].startswith("TW000" + code)):
            raise ValueError(f"wrong lifecycle state or security identity: {key}")
        identities[code].add(row["security_id"])
        if close:
            if price(row["raw_close"], 2) != Decimal(close):
                raise ValueError(f"wrong lifecycle raw close: {key}")
            price(row["adjusted_close"], 4)
        elif row["raw_close"] or row["adjusted_close"]:
            raise ValueError(f"nontrading lifecycle row contains a quote: {key}")
        expected_exchange = ("2884", "0.2596") if expected_status == "delisted" else ("", "")
        if (row["successor_code"], row["exchange_ratio"]) != expected_exchange:
            raise ValueError(f"wrong share exchange terms: {key}")
        observed[key] = row
    if observed.keys() != LIFECYCLE.keys() or any(len(ids) != 1 for ids in identities.values()):
        raise ValueError("missing milestone or inconsistent lifecycle ISIN")
    if identities["2867"] == identities["2884"]:
        raise ValueError("2867 and 2884 must remain distinct securities")


def verify_rights(raw):
    observed = set()
    for row in rows(raw, RIGHTS_COLUMNS):
        day = row["date"]
        if day in observed or row["code"] != "1312" or day not in RIGHTS_CLOSES:
            raise ValueError(f"unexpected or duplicate 1312 row: {day}")
        close = price(row["raw_close"], 2)
        alternate = price(row["adjusted_1320"], 4)
        official = price(row["adjusted_1340"], 4)
        factor = Decimal("13.40") / Decimal("13.20") if day < "2026-06-11" else Decimal(1)
        # The archived action list has no other 1312 price factor between these rows and the anchor.
        if (close != Decimal(RIGHTS_CLOSES[day])
                or alternate != close or abs(official - close * factor) > Decimal("0.00005")):
            raise ValueError(f"1312 close, anchor or dual adjustment factor differs on {day}")
        observed.add(day)
    if observed != RIGHTS_CLOSES.keys():
        raise ValueError("missing 1312 comparison date")


def verify_roster(raw, reference):
    members = {}
    for row in rows(raw, COLUMNS):
        day, code, identity = (row[field] for field in COLUMNS)
        if day != SESSION or code in members or not security_code(code) or not ISIN_PATTERN.fullmatch(identity):
            raise ValueError("roster contains an invalid date, code, ISIN or duplicate ticker")
        members[code] = identity
    if len(set(members.values())) != len(members):
        raise ValueError("roster contains duplicate security identities")
    canonical = "date,code,security_id\n" + "".join(
        f"{SESSION},{code},{identity}\n" for code, identity in sorted(members.items()))
    if (len(members) != reference["members"] or hashlib.sha256(canonical.encode()).hexdigest()
            != reference["canonical_roster_sha256"]):
        raise ValueError("roster does not match the same-source reference count and identity digest")


def verify(metadata, files, reference):
    if set(files) != set(FILES):
        raise ValueError("sample package must contain all three CSVs")
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    if not isinstance(metadata, dict) or hashes != metadata.get("sha256"):
        raise ValueError("one or more source bytes differ from the delivery SHA-256")
    required_text = ("supplier", "upstream_source", "export_version", "adjustment_method",
                     "license_reference", "usage_basis", "source_url")
    if (metadata.get("origin") not in ("external", "synthetic")
            or metadata.get("adjustment_anchor_date") != ANCHOR
            or metadata.get("market") != "TWSE" or metadata.get("currency") != "TWD"
            or any(not isinstance(metadata.get(field), str) or not metadata[field].strip()
                   for field in required_text)):
        raise ValueError("missing source, anchor, market, method or license information")
    uri = urlsplit(metadata["source_url"])
    if uri.scheme != "https" or not uri.hostname or uri.username or uri.password:
        raise ValueError("supplier source must be a credential-free HTTPS URL")
    permissions = metadata.get("permissions")
    if not isinstance(permissions, dict) or not all(
            permissions.get(key) is True for key in ("research", "retention", "replay")):
        raise ValueError("research, retention and replay permissions are required")
    verify_lifecycle(files["lifecycle"])
    verify_rights(files["rights"])
    verify_roster(files["roster"], reference)
    return dict(intake_status="PASS", origin=metadata["origin"], source_sha256=hashes,
                roster_members=reference["members"], coverage="three_samples_only",
                license_and_independence_review="REVIEW", historical_market_verified=False,
                score_eligible=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    reference_path = Path(__file__).resolve().parents[1] / "research" / "examples" / "supplier_sample" / "reference.json"
    try:
        reference = json.loads(reference_path.read_bytes())
        metadata = json.loads((args.directory / "manifest.json").read_bytes())
        files = {name: (args.directory / f"{name}.csv").read_bytes() for name in FILES}
        result = verify(metadata, files, reference)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps(dict(intake_status="FAIL", reason=str(exc), score_eligible=False), ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
