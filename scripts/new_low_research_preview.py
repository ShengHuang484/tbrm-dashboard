"""Render a dated research preview from the strict, non-scoring archive."""
import argparse
import json
from datetime import date
from pathlib import Path


def preview(report, gaps, rights, coverage, action):
    if any(doc.get("score_eligible") is not False for doc in (report, gaps, rights, action)):
        raise ValueError("research-only inputs required")
    sessions = report["sessions"]
    gap_by_date = {row["date"]: row for row in gaps["study_day_impact"]}
    changed = {row["date"]: row for row in rights["changed_sessions"]}
    dates = [row["date"] for row in sessions]
    if (report["lookback"] != 252 or report["quote_policy"] != "strict_market_sessions"
            or dates != report["market_dates"][252:] or dates != sorted(set(dates))
            or set(gap_by_date) != set(dates) or changed.keys() - set(dates)
            or rights["sessions"] != len(dates) or action["session"] in dates
            or coverage["denominator_sessions"] != len(report["market_dates"])):
        raise ValueError("research source dates or policy disagree")
    rows = {}
    for row in sessions:
        day = row["date"]
        eligible, active = row["eligible_count"], row["active_listings"]
        adjusted = row["adjusted_low_count"]
        gap = gap_by_date[day]
        alternative = changed.get(day, dict(original=adjusted, scenario=adjusted))
        if (not 0 <= adjusted <= eligible <= active or gap["known_lows"] != adjusted
                or eligible + gap["excluded_with_missing_close"] + row["insufficient_listing_age"] != active
                or alternative["original"] != adjusted or not 0 <= alternative["scenario"] <= eligible):
            raise ValueError(f"research source counts disagree: {day}")
        rows[day] = dict(status="research_only", raw_low=row["raw_low_count"],
                         adjusted_low=adjusted, eligible=eligible, active=active,
                         adjusted_low_share=adjusted / eligible if eligible else None,
                         cohort_coverage=eligible / active if active else None,
                         missing_close_exclusions=gap["excluded_with_missing_close"],
                         basis_1312_1340=adjusted, basis_1312_1320=alternative["scenario"],
                         basis_delta=alternative["scenario"] - adjusted)
    rows[action["session"]] = dict(status="BLOCKED" if action["status"] == "BLOCKED" else "unavailable")
    return dict(sessions=rows, historical_coverage=coverage,
                activation_blockers=["11/23 八類公司行動完整生效證據（A）",
                                     "262 日獨立逐日普通股母體、身分與還原行情（B）",
                                     "1312 正式價格口徑核准"],
                score_eligible=False)


def markdown(result):
    coverage = result["historical_coverage"]
    total = coverage["denominator_sessions"]
    lines = ["# 52 週新低研究預覽", "", "僅供研究。正式評分 45/50，score_eligible=false。", "",
             f"歷史母體內部重建 {coverage['internally_reconstructed_sessions']}／{total} 日，"
             f"外部獨立驗證 {coverage['external_independently_verified_sessions']}／{total} 日。"
             "表中母體覆蓋率為合格股數除以當日重建上市股數。", "",
             "| 交易日 | 狀態 | 原始新低 | 還原新低 | 合格／上市 | 新低占比 | 母體覆蓋率 | 缺價排除 | 1312：13.40／13.20（差） |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for day, row in sorted(result["sessions"].items()):
        if row["status"] != "research_only":
            lines.append(f"| {day} | {row['status']} | — | — | — | — | — | — | — |")
            continue
        low_share = format(row["adjusted_low_share"], ".2%") if row["adjusted_low_share"] is not None else "—"
        cohort = format(row["cohort_coverage"], ".2%") if row["cohort_coverage"] is not None else "—"
        lines.append(f"| {day} | 研究封存 | {row['raw_low']} | {row['adjusted_low']} |"
                     f" {row['eligible']}／{row['active']} | {low_share} | {cohort} |"
                     f" {row['missing_close_exclusions']} |"
                     f" {row['basis_1312_1340']}／{row['basis_1312_1320']} ({row['basis_delta']:+d}) |")
    lines += ["", "## 正式啟用尚缺", ""]
    lines += [f"- {item}" for item in result["activation_blockers"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("strict", "gaps", "rights", "roster_coverage", "action_coverage"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_bytes())
    result = preview(read(args.strict), read(args.gaps), read(args.rights),
                     read(args.roster_coverage)["coverage"], read(args.action_coverage))
    if args.date:
        day = args.date.isoformat()
        result["sessions"] = {day: result["sessions"].get(day, dict(status="unavailable"))}
    if args.format == "markdown":
        print(markdown(result), end="")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
