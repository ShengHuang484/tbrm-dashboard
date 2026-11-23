"""Point-in-time listing intervals for a research market universe."""
from collections import defaultdict
from datetime import date


def listing_windows(records):
    by_code = defaultdict(list)
    for row in records:
        code, start, end = row["code"], row["listed_from"], row["delisted_on"]
        if (not isinstance(code, str) or len(code) != 4 or not code.isascii()
                or not code.isdigit() or code.startswith("0")):
            raise ValueError("invalid listing code")
        for day in (start, end):
            if day is not None and date.fromisoformat(day).isoformat() != day:
                raise ValueError("invalid listing date")
        if start is None or (end is not None and end <= start):
            raise ValueError("invalid listing interval")
        by_code[code].append((start, end))
    for intervals in by_code.values():
        intervals.sort(key=lambda interval: interval[0])
        for (_, previous_end), (start, _) in zip(intervals, intervals[1:]):
            if previous_end is None or previous_end > start:
                raise ValueError("overlapping listing intervals")
    return by_code


def listings_on(windows, day):
    """Return the active interval per code, with an exclusive delisting date."""
    return {
        code: (start, end)
        for code, intervals in windows.items()
        for start, end in intervals
        if start <= day and (end is None or day < end)
    }
