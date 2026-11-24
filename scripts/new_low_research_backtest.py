"""Walk-forward evaluation of archived new-low features without affecting scoring."""
import argparse
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median

HORIZONS = (5, 10, 20, 60)
TRAIN, EMBARGO, TEST, MIN_BOTTOMS = 252, 60, 252, 20
PEAK_SESSIONS, BOTTOM_RADIUS = 5, 10
MODELS = ("A_baseline", "B_count", "C_share", "D_peak_contraction")


def features(report, index_rows, baseline):
    dates = sorted(index_rows)
    if (not dates or any(date.fromisoformat(day).isoformat() != day
                         or not math.isfinite(index_rows[day]) or index_rows[day] <= 0 for day in dates)):
        raise ValueError("market calendar needs ISO dates and positive closes")
    rows = report["sessions"]
    if report["score_eligible"] is not False or report["lookback"] != 252:
        raise ValueError("expected strict research archive")
    study_dates = [row["date"] for row in rows]
    if (study_dates != sorted(set(study_dates)) or set(study_dates) - set(dates)
            or report["quote_policy"] != "strict_market_sessions"):
        raise ValueError("research sessions must align with the supplied market calendar")
    archived_calendar = report["market_dates"]
    first, last = max(dates[0], archived_calendar[0]), min(dates[-1], archived_calendar[-1])
    if ([d for d in dates if first <= d <= last] !=
            [d for d in archived_calendar if first <= d <= last]):
        raise ValueError("inconsistent market sessions in the overlapping archives")
    archive_by_day = {row["date"]: row for row in rows}
    result = []
    for i, day in enumerate(dates):
        row, score = archive_by_day.get(day), baseline.get(day)
        if row is None:
            continue
        stage = dict(index=i, date=day, count=row["adjusted_low_count"], share=None, contraction=None)
        eligible = row["eligible_count"]
        if not 0 <= stage["count"] <= eligible:
            raise ValueError("invalid research breadth values")
        if eligible:
            stage["share"] = stage["count"] / eligible
        previous = dates[max(i - PEAK_SESSIONS, 0):i]
        if len(previous) == PEAK_SESSIONS and all(d in archive_by_day for d in previous):
            peak = max(archive_by_day[d]["adjusted_low_count"] for d in previous)
            stage["contraction"] = max(0, peak - stage["count"]) / peak if peak else 0
        if score is not None:
            value = score["confirmation_score"]
            if score["available_on"] != day or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError(f"baseline must be a dated as-of-close score: {day}")
            indicators = score.get("indicator_scores", {})
            if any(not math.isfinite(v) for v in indicators.values()):
                raise ValueError(f"invalid point-in-time indicator: {day}")
            stage.update(baseline=value, indicators=indicators)
        result.append(stage)
    return dates, result


def rank(value, history):
    return (sum(x < value for x in history) + 0.5 * sum(x == value for x in history)) / len(history)


def predictions(rows, calendar_size):
    # Walk-forward ranks use the prior scheduled observations, never outcomes
    # or the feature values of the scoring session or later sessions.
    complete = [row for row in rows if "baseline" in row
                and row["share"] is not None and row["contraction"] is not None]
    keys = ("baseline", "count", "share", "contraction")
    result = []
    start = 0
    for j, row in enumerate(complete):
        while start < j and complete[start]["index"] < row["index"] - EMBARGO - TRAIN:
            start += 1
        train = [old for old in complete[start:j] if old["index"] < row["index"] - EMBARGO]
        if len(train) < TRAIN or row["index"] + max(HORIZONS) >= calendar_size:
            continue
        p = [rank(row[k], [old[k] for old in train]) for k in keys]
        scores = [p[0], *((p[0] + x) / 2 for x in p[1:])]
        result.append(dict(row, train_end=train[-1]["date"],
                           signals={name: score >= 0.8 for name, score in zip(MODELS, scores, strict=True)}))
    return result


def bottom_days(prices):
    """Retrospective target. Future closes only enter outcome measurement."""
    return [
        i for i in range(BOTTOM_RADIUS, len(prices) - 20)
        if prices[i] == min(prices[i - BOTTOM_RADIUS:i + BOTTOM_RADIUS + 1])
        and prices[i] < prices[i - 1] and prices[i + 20] / prices[i] >= 1.05
    ]


def regime(prices, i):
    change = prices[i] / prices[i - 20] - 1 if i >= 20 else 0
    return "rising" if change > .03 else "falling" if change < -.03 else "range"


def measures(points, prices, bottoms, model):
    signals = [p["index"] for p in points if p["signals"][model]]
    # Associate each target with at most one signal in the predeclared window.
    candidates = sorted((abs(i - b), i, b) for i in signals for b in bottoms
                        if abs(i - b) <= BOTTOM_RADIUS)
    used_signals, used_bottoms, offsets = set(), set(), []
    for _, i, b in candidates:
        if i not in used_signals and b not in used_bottoms:
            used_signals.add(i)
            used_bottoms.add(b)
            offsets.append(i - b)
    sample = len(signals)
    return dict(signals=sample, bottom_events=len(bottoms), matched=len(offsets),
                precision=len(offsets) / sample if sample else None,
                recall=len(offsets) / len(bottoms) if bottoms else None,
                false_signal_rate=1 - len(offsets) / sample if sample else None,
                median_signal_minus_bottom_sessions=median(offsets) if offsets else None,
                horizons={str(h): dict(
                    observations=sample,
                    mean_return=mean(prices[i + h] / prices[i] - 1 for i in signals) if sample else None,
                    worst_adverse_close=min(
                        min(prices[i:i + h + 1]) / prices[i] - 1 for i in signals) if sample else None,
                ) for h in HORIZONS})


def correlations(rows):
    names = ("count", "share", "contraction")
    comparisons = {"baseline": [(row, row["baseline"]) for row in rows]}
    extras = defaultdict(list)
    for row in rows:
        for key, value in row["indicators"].items():
            extras[key].append((row, value))
    comparisons.update({f"indicator:{key}": values for key, values in extras.items()})
    result = {}
    for key, pairs in comparisons.items():
        result[key] = {}
        for name in names:
            x, y = [r[name] for r, _ in pairs], [v for _, v in pairs]
            r = None
            if len(x) >= 3 and len(set(x)) > 1 and len(set(y)) > 1:
                mx, my = mean(x), mean(y)
                dx, dy = [v - mx for v in x], [v - my for v in y]
                r = sum(a * b for a, b in zip(dx, dy, strict=True)) / math.sqrt(
                    sum(a * a for a in dx) * sum(b * b for b in dy))
            result[key][name] = dict(n=len(pairs), pearson=r)
    return result


def evaluate(report, index_rows, baseline):
    dates, rows = features(report, index_rows, baseline)
    prices = [index_rows[day] for day in dates]
    points = predictions(rows, len(dates))
    point_indexes = {row["index"] for row in points}
    bottoms = [i for i in bottom_days(prices) if i in point_indexes]
    counts = dict(research_sessions=len(rows), market_index_sessions=len(dates),
                  dated_baseline_sessions=sum("baseline" in row for row in rows),
                  contraction_sessions=sum(row["contraction"] is not None for row in rows),
                  future_close_windows={str(h): sum(row["index"] + h < len(dates) for row in rows)
                                        for h in HORIZONS},
                  out_of_sample_sessions=len(points), out_of_sample_bottoms=len(bottoms))
    report = dict(status="INSUFFICIENT_SAMPLE", counts=counts,
                  requirements=dict(prior_training=TRAIN, embargo=EMBARGO,
                                    test_observations=TEST, target_events=MIN_BOTTOMS,
                                    forward_calendar_sessions=max(HORIZONS)),
                  metrics=None, score_eligible=False)
    if len(points) < TEST or len(bottoms) < MIN_BOTTOMS:
        return report
    parts = {"overall": points}
    for offset in range(0, len(points), 84):
        group = points[offset:offset + 84]
        parts[f"chronological:{group[0]['date']}..{group[-1]['date']}"] = group
    for name in ("rising", "falling", "range"):
        parts[f"regime:{name}"] = [p for p in points if regime(prices, p["index"]) == name]
    report.update(status="EXPLORATORY", metrics={}, feature_overlap=correlations(points))
    for name, group in parts.items():
        indices = {p["index"] for p in group}
        targets = [t for t in bottoms if t in indices]
        report["metrics"][name] = dict(
            sessions=len(group), models={model: measures(group, prices, targets, model) for model in MODELS})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strict", type=Path)
    parser.add_argument("index", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    index = json.loads(args.index.read_bytes())["rows"]
    baseline = json.loads(args.baseline.read_bytes()) if args.baseline else {}
    index_rows = {r["date"]: float(r["close"]) for r in index}
    if len(index_rows) != len(index):
        raise ValueError("duplicate market index date")
    result = evaluate(json.loads(args.strict.read_bytes()), index_rows, baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
