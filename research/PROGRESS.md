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

## 2026-11-23 個股日期與非配息來源查核

- 已為 10 筆異常建立[逐檔查核表](effective_date_crosscheck.md)。7 筆有券商復市日期、前收對照值與參考價佐證。4968 的外部金額衝突、5519 的現金加股票股利價格基準、6931 的正式參考價仍待查。正式事件資料保留原始日期。
- 已定位證交所 [TWTAUU 減資恢復買賣參考價格](https://www.twse.com.tw/zh/announcement/reduction/twtauu.html)。報表有復市日、停牌前收盤價、復市參考價與除權參考價。含現增的減資需核對兩個參考價所屬的交易階段。合併須用[終止上市及新股上市紀錄](https://twse-regulation.twse.com.tw/tw/law/DOC01.aspx?FLCODE=FL007304&FLNO=53-1)核對證券前後身。全期間減資、分割、反分割與合併仍缺逐筆清單與獨立覆蓋核對。

## 2026-11-23 調整係數、缺價政策與基準比對

- 新增 `python -m scripts.new_low_adjusted_audit <raw-history.json> <verified-events.json>`。調整係數以參考價除以前收計算，採精確分數，僅回乘生效日前的行情。事件需具備上游驗證標記、能對應生效日行情，且事件前收必須與最近一筆原始收盤一致。缺漏事件仍可能使結果偏誤。正式評分維持 45/50。
- 研究缺價政策採每日嚴格 252 個市場交易日。當日有有效報價且 252 筆先前報價齊全的股票才進入當日分母；缺一筆即排除，不插補、不沿用舊價。相等不計新低。結果同時報告當日有報價、可納入及回看期缺報價數。缺價原因、上市或下市日期及實際上市股票母體仍需另行確認。
- 獨立程式以同一份原始資料重算 10 個交易日，逐日吻合既有原始新低檔數、分母與排除數。最後一日為 483 檔新低、946 檔納入、144 檔因缺報價排除。合成案例覆蓋連續事件、精確相等、缺價排除及未來事件隔離。全套本地測試 53 項通過。這項比對驗證計算邏輯，獨立市場資料的調整後基準仍待建立。

## 2026-11-23 全期間減資報表擷取

- 新增 TWTAUU 減資候選清冊擷取。按原始收盤檔的完整日期範圍查詢，檢查回應期間、欄名及重複事件，留存原始回應、雜湊及兩類參考價。工作區直接連線逾時，使用研究分支的只讀 Actions 擷取。
- 分割或反分割的普通股另查[變更股票面額及換發公告](https://www.twse.com.tw/zh/announcement/change/cal.html)。ETF 分割清單的證券範圍不同。合併另以證券前後身的上市與終止上市紀錄核對。本地測試 55 項通過，整體公司行動完整性仍需獨立比對。
