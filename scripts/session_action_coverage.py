"""Assess effective-date coverage of the archived November 23 source responses."""

import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from scripts.new_low_session_probe import compare_action_windows, evidence_report
from scripts.twse_corporate_action_parser import roc_date

REPLAY_INPUTS = ("quotes", "calendar", "isin_prefix", "isin_full", "tib", "tib_isin",
                 "tdr_isin", "reduction", "ex_right", "stock_1538",
                 "ex_window", "reduction_window")
PAR_REPORTS = ("par_rwd_change", "par_legacy_range")


def action_date_control(payload, field, start, end):
    fields = payload["fields"]
    if payload["stat"] != "OK" or len(fields) != len(set(fields)) or field not in fields:
        raise ValueError(f"missing or ambiguous date field: {field}")
    values = [dict(zip(fields, raw, strict=True))[field] for raw in payload["data"]]
    observed = sorted({roc_date(value.replace(".", "/")) for value in values if value})
    return dict(effective_date_field=field, observed_dates=observed,
                outside_window=[day for day in observed if not start <= day <= end],
                rows_without_effective_date=sum(not value for value in values))


def audit(day, inputs, source_manifest, replay, reduction_terms):
    hashes = {}
    for name, raw in inputs.items():
        evidence = source_manifest[name]
        if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
            raise ValueError(f"archived bytes differ for {name}")
        hashes[name] = evidence["sha256"]

    reduction = json.loads(inputs["reduction"])
    reduction_rows = [dict(zip(reduction["fields"], row, strict=True)) for row in reduction["data"]]
    windows, _ = compare_action_windows(day, inputs, reduction_rows)
    ex_window = windows["ex_window"]
    controls = ex_window["observed_codes_by_date"]
    if not (any(d < day for d in controls) and any(d > day for d in controls)):
        raise ValueError("ex-right positive controls on both sides are required")
    compact = day.replace("-", "")
    if json.loads(inputs["ex_right"]) != {"stat": replay["ex_right_response"]}:
        raise ValueError("single-day empty response has changed")
    start, end = [datetime.strptime(ex_window[key], "%Y%m%d").date().isoformat()
                  for key in ("start", "end")]
    par = {}
    for name in PAR_REPORTS:
        body = json.loads(inputs[name])
        control = action_date_control(body, "恢復買賣日期", start, end)
        params = body["params"]
        control["requested_bounds_echoed"] = (
            [params.get("startDate"), params.get("endDate")] ==
            [ex_window["start"], ex_window["end"]]
        )
        par[name] = control
    newlisting = json.loads(inputs["newlisting"])
    listing = action_date_control(newlisting, "股票上市買賣日期", start, end)
    listing["session_in_observed_dates"] = day in listing["observed_dates"]
    listing.pop("observed_dates")
    listing["outside_window"] = len(listing["outside_window"])
    mops = json.loads(inputs["mops_disclosures"])
    filing_dates = sorted({row["出表日期"] for row in mops})
    announcement_dates = sorted({row["發言日期"] for row in mops})
    statement_dates = sorted({row["事實發生日"] for row in mops})
    roc_today = str(int(compact[:4]) - 1911) + compact[4:]
    disclosure = dict(snapshot_matches_session=filing_dates == [roc_today],
                      filing_dates=filing_dates, announcement_dates=announcement_dates,
                      reported_fact_dates=statement_dates, exchange_effective_date_field=False)

    matches = [row for row in replay["reduction_observations"] if row["code"] == reduction_terms["code"]]
    if len(matches) != 1:
        raise ValueError("known reduction positive control is missing")
    control = matches[0]
    calculated = ((Decimal(control["old_close"]) - Decimal(reduction_terms["refund_per_old_share"]))
                  / Decimal(reduction_terms["new_shares_per_old_share"]))
    if calculated != Decimal(control["exchange_reference"]):
        raise ValueError("known reduction reference does not match the calculation")

    def finding(status, sources, limit):
        return dict(status=status, sources=sources, full_scope_attested=False, limit=limit)

    matrix = {
        "ex_rights_and_dividends": finding("PARTIAL", ["ex_right", "ex_window"],
            "Adjacent effective dates confirmed; empty day response has no scope declaration."),
        "capital_reduction": finding("PARTIAL", ["reduction", "reduction_window"],
            "Window and daily rows agree; no proof that other replacement or adjustment classes are included."),
        "par_value_change": finding("BLOCKED", list(PAR_REPORTS),
            "Preannouncement rows occur outside echoed range."),
        "split": finding("BLOCKED", list(PAR_REPORTS), "No complete date-scoped split register."),
        "reverse_split": finding("BLOCKED", list(PAR_REPORTS), "No complete date-scoped reverse-split register."),
        "share_conversion": finding("BLOCKED", ["mops_disclosures", "newlisting"],
            "Filing and fact dates do not establish exchange effectiveness."),
        "merger": finding("BLOCKED", ["mops_disclosures", "newlisting"],
            "No complete session register of mergers and trading dispositions."),
        "replacement_shares": finding("BLOCKED", ["newlisting", "mops_disclosures", *PAR_REPORTS],
            "Initial listing records omit continuing issuers' replacement shares."),
    }
    return dict(session=day, status=replay["status"], replay_error=replay["replay_error"],
                checkpoint_sha256=replay["checkpoint_sha256"],
                source_sha256=hashes, window_controls=windows, par_value_controls=par,
                initial_listing_date_control=listing, disclosure_date_control=disclosure,
                capital_reduction_positive_control=dict(control, status="PASS",
                                                        formula_reference=str(calculated)),
                coverage_matrix=matrix, score_eligible=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("checkpoint", "raw_directory", "supplemental_directory"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    day = "2026-11-23"
    root = Path(__file__).resolve().parents[1] / "research"
    acceptance = json.loads((root / "incremental_acceptance_20261123.json").read_bytes())
    windows = json.loads((root / "incremental_action_windows_20261123.json").read_bytes())
    supplemental = json.loads((root / "incremental_scope_followup_20261123.json").read_bytes())
    inputs = {name: (args.raw_directory / f"{name}.raw").read_bytes() for name in REPLAY_INPUTS}
    checkpoint = args.checkpoint.read_bytes()
    if hashlib.sha256(checkpoint).hexdigest() != acceptance["checkpoint_sha256"]:
        raise ValueError("checkpoint differs from the archived 11/23 pre-session checkpoint")
    for name, evidence in acceptance["sources"].items():
        if hashlib.sha256(inputs[name]).hexdigest() != evidence["sha256"]:
            raise ValueError(f"archived session input differs for {name}")
    replay = evidence_report(day, checkpoint, inputs, identity_retrieved_on=day)
    inputs = {name: inputs[name] for name in ("ex_right", "ex_window", "reduction", "reduction_window")}
    for name in (*PAR_REPORTS, "newlisting"):
        inputs[name] = (args.supplemental_directory / f"{name}.raw").read_bytes()
    inputs["mops_disclosures"] = (args.raw_directory / "mops_disclosures.raw").read_bytes()
    manifest = acceptance["sources"] | windows["sources"] | {"mops_disclosures": supplemental["disclosure_probe"]}
    result = audit(day, inputs, manifest, replay, windows["reduction_reference_crosscheck"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
