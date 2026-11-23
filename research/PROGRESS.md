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

## 2026-11-23 第一次正式減資報表與原始除權息月報比對

- [減資 Actions](https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45100965405) 擷取 2025-10-22 至 2026-11-20 共 21 筆減資復市候選事件。原始 JSON SHA-256 為 `92621534a0f488aadd3760809bc10441a79aa0070df8aadbdb75e69fdec77abf`。21 筆有復市日原始收盤，20 筆停牌前收盤與原始歷史精確一致，這 20 筆的報價缺口為 6–7 個交易日。2832 的停牌前收早於原始檔起點，[元大減資日程表](https://www.yuanta.com.tw/eYuanta/Securities/News/GetAPItem?Type=StockHotNews&id=202511030082542)支持 11/03 復市，仍需補更早原始歷史以驗證前收。
- 期末仍有報價的 20 檔減資候選股票中，只有 1 檔進入嚴格 252 日分母。這量化了採該缺價政策的選樣影響。報價原因全分類、放寬政策的敏感度、上市母體獨立核對仍待完成。
- 舊 [除權息來源封存](https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45059710691) 的 10 筆原日期前收全數吻合復市前本地原始收盤。已補上[逐檔價格](effective_date_crosscheck.md)，其中 2610、2891 與券商參考價差 0.01 元，5519 可用現金及股票股利公式重建官方參考價。正式日期改派仍保留待審。原始 TWT49U 封存始自 2025-11，尚需查 2025-10-22 至月底以對齊原始收盤起點。
- [研究分支 CI](https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45100965266) 通過。後續仍需涵蓋普通股分割、反分割及合併事件，並取得外部調整後價格或新低檔數作獨立基準。

## 2026-11-23 普通股分割及上市身分核對

- [證交所 TWTB7U](https://www.twse.com.tw/exchangeReport/TWTB7U?date=undefined&response=html&selectType=undefined)列出 6949 沛爾生醫 2026-09-07 以 20 倍股數換發。[發行公司公告](https://goodinfo.tw/tw/StockAnnounceDetail.asp?CLAIM_TIME=2026%2F09%2F02+07%3A00%3A03&STOCK_ID=6949&SUBJECT=%E5%85%AC%E5%91%8A%E6%9C%AC%E5%85%AC%E5%8F%B8%E8%82%A1%E7%A5%A8%E9%9D%A2%E9%A1%8D%E7%94%B1%E3%80%8C%E6%96%B0%E5%8F%B0%E5%B9%A310%E5%85%83%E3%80%8D%E8%AE%8A%E6%9B%B4%E7%82%BA%E3%80%8C%E6%96%B0%E5%8F%B0%E5%B9%A30.5%E5%85%83%E3%80%8D)也明示用 8/26 收盤除以 20。原始前收 1,490，理論參考價 74.50，復市收盤 67.10，係數為 1/20。一筆普通股分割有交易所和發行公司佐證。TWTB7U 是預告表，仍需查歷史涵蓋期間及反分割。
- 比對[證交所終止上市清單](https://www.twse.com.tw/company/suspendListingCsvAndHtml?lang=zh&type=html)，窗口內列有 6423、3454、6806、2867、1589，五檔原始報價均早於終止上市日結束。3454 [由台達電以現金進行股份轉換](https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d69c37647f019c89fca2900063.pdf)，不應把兩證券歷史串接。1589 為[財報一案的終止上市](https://investoredu.twse.com.tw/FileSystem/FileUpload/d0048d9a-e912-42ee-9c32-7a5bbff1d010.pdf)。其餘個案、窗口內新上市和代碼承繼、倖存公司事件仍需獨立核對。
- 已加上原始行情起始月的 TWT49U 擷取，補查原封存未包含的 2025-10-22 至月底。調整後的整體市場基準仍欠第二份涵蓋同期間且價格定義一致的資料。

## 2026-11-23 起始月封存、外部還原價與缺價敏感度

- 起始月[封存 Actions](https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45101315461)取得 57 筆全證券日期列。依現有普通股代碼規則和原始行情窗口篩選，剩 7 筆，其中 6 筆前收精確吻合。1589 事件恰在原始行情首日，無窗口內前收，對窗口內任何歷史價格都不套用該事件。納入完整性清單時仍保留該筆。原始檔 SHA-256 為 `5f446fde77c72f421e57a8b2194a1ce6ede013fff9843b8bde395ecb703a200f`。
- 6949 的 20 比 1 分割前後，6 筆本地原始收盤經計算後均精確吻合 [Goodinfo 還原股價](https://goodinfo.tw/tw/ShowBuySaleChart.asp?CHT_CAT=DATE&PRICE_ADJ=T&STOCK_ID=6949)，已加入固定值回歸測試。全套本地測試 56 項通過。獨立核對已完成這一檔的樣本，市場級調整後新低仍未驗證。
- 原始價格敏感度比較中，允許向前找最近 252 筆有效報價，期末分母從 946 增至 1,040，原始新低從 483 增至 520。這項對照允許拉長回看日曆跨度，不插補價格，也不變更嚴格研究預設。正式採用前仍需用獨立上市及停牌紀錄驗證選樣影響。
- 終止上市五檔的原因已查齊。6423 轉櫃、3454 為現金股份轉換、6806 為負淨值、2867 與玉山金換股、1589 為財報未補正。2867 的原始行情於 8/19 結束，也與[公司對外說明](https://www.cna.com.tw/news/afe/202607130297.aspx)吻合。6423、6806 的原因見[轉櫃公告](https://wwwc.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d69a3d6cf9019bc625f80f075e.pdf)及[負淨值公告](https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d69dbea9fd019e212d55f901ef.pdf)。五筆原因的核對尚不能證明所有合併及存續方公司行動已涵蓋。
- 仍欠 10 筆異常的可重現正式生效日、減資清冊第二來源、普通股分割／反分割／合併全期間清冊，以及同口徑外部市場基準。維持 `score_eligible=false` 與 45/50。

## 2026-11-23 復市日官方逐檔查詢

- 以既有封存檔建立 10 筆逐檔輸入，保留原日期、復市候選日、前收、官方參考價及開盤競價基準。新增研究 Actions 查兩個復市日的 TWSE MI_INDEX 與單日 TWT49U，保留原始 JSON 與 SHA-256。交易日及報表範圍有獨立檢查。依[證交所每日收盤行情說明](https://www.twse.com.tw/zh/trading/historical/mi-index.html)，無比價有多種原因，程式保留觀察值供核對。
- 本地測試 57 項通過。復市日的正式資料擷取結果待 Actions。研究輸出維持 `score_eligible=false`。

## 2026-11-23 逐檔復市日與基準價格查核結果

- [官方復市日 Actions](https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45102137373) 回傳 10/10 筆行情。用收盤價減帶符號漲跌價差重建價格基準，10/10 精確吻合原 TWT49U 的開盤競價基準，且 10/10 都與一般前收不同。確認 7/13 八檔及 10/27 兩檔的實際交易已使用對應的除權息基準。[逐檔 JSON](ex_right_date_results.json) 保存原報表、官方復市行情、參考價、競價基準及原始資料 SHA-256。
- 2610、2891 的原官方除息參考價仍為 20.58、67.39，實際交易競價基準為 20.60、67.40。6931 的 37.38 與 37.40 也屬不同欄位。回調係數取參考價，不用競價基準或復市收盤價。單日 TWT49U 查詢仍無這 10 筆修訂列，因此保存原報告日期與由復市交易反推的生效日期，未直接修改評分來源。60 項本地測試通過。
