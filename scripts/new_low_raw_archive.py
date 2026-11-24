"""Save research source responses without loading or advancing a checkpoint."""
import argparse
import hashlib
import json
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from scripts.new_low_incremental import QUOTE_URL, parse_closes
from scripts.new_low_session_probe import (ISIN_URL, TDR_ISIN_URL, TIB_ISIN_URL,
                                          check_full_isin, ordinary_isin_prefix, scoped_isins)
from scripts.twse_corporate_action_parser import roc_date
from scripts.twse_stock_day_gaps import capture, replay_evidence, source_url

TAIPEI = ZoneInfo("Asia/Taipei")
MAX_BYTES = 24 * 1024 * 1024


def endpoints(day):
    compact = day.replace("-", "")
    bounds = f"response=json&startDate={compact}&endDate={compact}"
    return {
        "quotes": QUOTE_URL + compact,
        "calendar": "https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date=" + compact[:6] + "01",
        "isin_full": ISIN_URL, "tib_isin": TIB_ISIN_URL, "tdr_isin": TDR_ISIN_URL,
        "ex_right": f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?{bounds}",
        "reduction": f"https://www.twse.com.tw/exchangeReport/TWTAUU?{bounds}",
        "par_value": f"https://www.twse.com.tw/rwd/zh/change/TWTB7U?{bounds}",
        "newlisting": f"https://www.twse.com.tw/rwd/zh/company/newlisting?response=json&yy={int(day[:4]) - 1911}",
        "mops_disclosures": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
    }


def download(_name, url):
    req = Request(url, headers={"User-Agent": "TBRM research archive/1.0"})
    with urlopen(req, timeout=20) as response:
        if urlsplit(response.url).scheme != "https":
            raise ValueError("source redirected outside HTTPS")
        return response.read(MAX_BYTES + 1)


def event_observation(raw, day, field):
    body = json.loads(raw)
    compact = day.replace("-", "")
    fields = body.get("fields", [])
    if (body.get("stat") != "OK" or field not in fields
            or body.get("strDate") != compact or body.get("endDate") != compact):
        return dict(status="unconfirmed_scope", response_status=body.get("stat"))
    index = fields.index(field)
    dates = sorted({roc_date(row[index]) for row in body["data"]})
    return dict(status="dated_rows" if dates == [day] else "unconfirmed_scope",
                observed_effective_dates=dates)


def archive(day, root, fetch, *, source_date, mode, provenance=None):
    if (date.fromisoformat(day).isoformat() != day or date.fromisoformat(source_date).isoformat() != source_date):
        raise ValueError("dates must be YYYY-MM-DD")
    if mode not in ("live", "archived_import") or (mode == "archived_import") != (provenance is not None):
        raise ValueError("import requires recorded source provenance")
    session = root / day
    session.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix="capture-", dir=session))
    entries = {}
    observations = {}

    def save(name, url):
        entry = entries[name] = dict(requested_url=url)
        try:
            if provenance is None:
                observed = datetime.now(TAIPEI)
                entry.update(url=url, source_capture_date=observed.date().isoformat(),
                             retrieved_at=observed.isoformat(timespec="seconds"))
            else:
                record = provenance.get(name)
                if not record:
                    raise ValueError("source provenance is unavailable")
                uri = urlsplit(record["url"])
                if uri.scheme != "https" or not uri.hostname:
                    raise ValueError("invalid recorded source URL")
                captured = record.get("source_capture_date", source_date)
                if date.fromisoformat(captured).isoformat() != captured:
                    raise ValueError("invalid recorded capture date")
                entry.update(url=record["url"], source_capture_date=captured)
            raw = fetch(name, entry["url"])
            if provenance is not None and hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("raw bytes differ from recorded source SHA-256")
            if not raw or len(raw) > MAX_BYTES:
                raise ValueError("source body empty or over byte limit")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            entry.update(status="unavailable", error=str(exc))
            return None
        (attempt / f"{name}.raw").write_bytes(raw)
        entry.update(status="saved", bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        return raw

    def inspect(name, run):
        try:
            observations[name] = run()
        except (ValueError, KeyError, AttributeError, IndexError, TypeError) as exc:
            observations[name] = dict(status="unverified", error=str(exc))

    raw = {name: save(name, url) for name, url in endpoints(day).items()}
    prices, members, known_tdr = {}, {}, set()

    def quotes():
        prices.update(parse_closes(json.loads(raw["quotes"]), day))
        return dict(status="dated", observed_date=day, symbols=len(prices))

    def calendar():
        body = json.loads(raw["calendar"])
        if body.get("stat") != "OK" or body.get("date") != day.replace("-", "")[:6] + "01":
            raise ValueError("calendar response month differs")
        dates = [roc_date(row[0]) for row in body["data"]]
        if dates != sorted(set(dates)) or any(d[:7] != day[:7] for d in dates):
            raise ValueError("calendar dates disagree with requested month")
        return dict(status="observed_open" if day in dates else "not_yet_observed",
                    observed_last_date=max(dates, default=None))

    def roster():
        if any(entries[name].get("source_capture_date") != day
               for name in ("isin_full", "tib_isin", "tdr_isin")):
            raise ValueError("current ISIN snapshot was not captured on requested date")
        general = ordinary_isin_prefix(raw["isin_full"], day)
        tib = scoped_isins(raw["tib_isin"], "上市臺灣創新板", "創新板", "ES")
        tdr = scoped_isins(raw["tdr_isin"], "上市", "臺灣存託憑證(TDR)", "ED")
        info = check_full_isin(raw["isin_full"], day, general, tib, tdr)
        if general.keys() & tib.keys() or len({r["security_id"] for r in (general | tib).values()}) != len(general) + len(tib):
            raise ValueError("ordinary-share identities overlap")
        members.update(general | tib)
        known_tdr.update(tdr)
        return dict(status="dated", observed_date=day, ordinary_shares=len(members), **info)

    inspect("quotes", quotes)
    inspect("calendar", calendar)
    inspect("roster", roster)
    for name, field in (("ex_right", "資料日期"), ("reduction", "恢復買賣日期")):
        inspect(name, lambda name=name, field=field: event_observation(raw[name], day, field))

    gaps = {}
    if prices and members:
        for code in sorted(c for c in members if prices.get(c) is None):
            name = f"stock_{code}"
            body = save(name, source_url(code, day[:7]))
            try:
                evidence = capture(code, day[:7], [day], body)
                gaps[code] = dict(replay_evidence([evidence]))[(code, day)]
            except (ValueError, KeyError, AttributeError, IndexError, TypeError):
                gaps[code] = "unverified"
    observations["gaps"] = dict(
        status="observed" if prices and members and "unverified" not in gaps.values() else "unverified",
        codes=gaps)
    observations["other_action_sources"] = dict(status="archived_for_review", sources=[
        name for name in ("par_value", "newlisting", "mops_disclosures") if raw[name] is not None])
    observations["tdr_quote_codes"] = sorted(prices.keys() & known_tdr) if prices and members else None
    observations["unexpected_quote_codes"] = (
        sorted(prices.keys() - members.keys() - known_tdr) if prices and members else None)

    manifest = dict(session=day, mode=mode, source_capture_date=source_date, sources=entries,
                    observations=observations, action_coverage_reviewed=False, score_eligible=False)
    (attempt / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    return attempt


def verify(attempt):
    manifest = json.loads((attempt / "manifest.json").read_bytes())
    if manifest["action_coverage_reviewed"] is not False or manifest["score_eligible"] is not False:
        raise ValueError("raw archive must not attest action coverage or scoring")
    expected = set()
    required = endpoints(manifest["session"])
    if not required.keys() <= manifest["sources"].keys():
        raise ValueError("incomplete archive source inventory")
    for name, entry in manifest["sources"].items():
        if name not in required and not (
                name.startswith("stock_") and len(name) == 10 and name[6:].isascii() and name[6:].isdigit()):
            raise ValueError("invalid archive source name")
        if entry["status"] == "unavailable":
            continue
        filename = f"{name}.raw"
        expected.add(filename)
        raw = (attempt / filename).read_bytes()
        if entry["status"] != "saved" or len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"archive hash or size differs: {name}")
    if expected != {path.name for path in attempt.glob("*.raw")}:
        raise ValueError("unexpected or missing archive files")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "import"):
        sub = commands.add_parser(command)
        sub.add_argument("session")
        sub.add_argument("archive_root", type=Path)
        if command == "import":
            sub.add_argument("source_directory", type=Path)
            sub.add_argument("--source-capture-date", required=True)
            sub.add_argument("--source-manifest", required=True, type=Path)
    check = commands.add_parser("verify")
    check.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        manifest = verify(args.directory)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    if args.command == "collect":
        now = datetime.now(TAIPEI)
        if args.session != now.date().isoformat() or now.time() < time(16):
            parser.error("live collection requires today's Taipei date and 16:00 or later")
        attempt = archive(args.session, args.archive_root, download,
                          source_date=now.date().isoformat(), mode="live")
    else:
        attempt = archive(args.session, args.archive_root,
                          lambda name, _url: (args.source_directory / f"{name}.raw").read_bytes(),
                          source_date=args.source_capture_date, mode="archived_import",
                          provenance=json.loads(args.source_manifest.read_bytes()))
    verify(attempt)
    print(attempt)


if __name__ == "__main__":
    main()
