# TBRM 52-week new-low research progress (2026-11-23)

This document tracks evidence, not a guarantee of completion or an authorization to enable scoring.

| Workstream | Evidence | State | Remaining effort estimate |
| --- | --- | --- | --- |
| 262-day raw TWSE close history | 262 dates, 1,097 distinct stock codes, no invalid closes | Structural check passed | 0 h |
| Prior-close reconciliation | 951/961 exact; 10 date conflicts | Price basis checked; event validity not certified | 2–5 h |
| Internal missing quote cross-check | 234/234 dates; 810 stock/date gaps; 615 rows without valid close, 195 absent from detail, 0 recoverable quotes | Source comparison complete; absence/suspension cause unverified | 1–3 h |
| Strict 252-prior-day universe | 946/1,090 latest-day stocks eligible; 144 not eligible | Diagnostic complete; universe policy not approved | 1–3 h |
| Corporate action completeness | Ex-rights/dividend source available; capital reduction, split, consolidation, merger not independently complete | Blocking | 4–10 h |
| Adjusted new-low series | Verified factor coverage incomplete | Blocking | 2–5 h |
| Backtest and live score activation | No independently validated adjusted series | Blocking | 3–6 h |

**Remaining work estimate:** 13–32 hours of active investigation/implementation, excluding waiting for external evidence. This is a planning range, not an SLA. Some tasks can overlap, and unresolved data could extend the schedule.

## Evidence references
- Complete quote gap audit: https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45060767072
- Consolidated readiness: https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45059710691
- Typhoon date candidate research: research/typhoon_event_date_evidence.json

## Activation criteria
- [ ] Independent per-security effective-date confirmation for all 10 anomalies
- [ ] Complete independent corporate-action coverage including non-dividend events
- [ ] Verified backward adjustment factors and validated 52-week-low counts
- [ ] Defensible missing-quote / listing-universe treatment
- [ ] Independent baseline comparison and regression tests
- [ ] Explicit review and approval before production merge

Until then **score_eligible=false; live score=45/50**. Do not merge research into main as production scoring.
