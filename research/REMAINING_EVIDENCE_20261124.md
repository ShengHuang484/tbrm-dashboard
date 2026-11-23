# 上市起日及 11/23 生效資料驗收

## 四筆上市起日差異

原始欄代表封存研究區間使用的 TWSE 日期，候選欄代表已觀察到的 ISIN 起日。PARTIAL 表示有可保留的上市日期主證，候選欄位語意仍未釐清。

| 證券 | 原始／候選 | 日期定義與原始證據 | 結果 | 252 日資格／新低成員變動 |
|---|---|---|---|---|
| 1303 南亞 | 1967/11/15／1967/11/05 | TWSE 個股頁及發行人現行簡介列 11/15，發行人年報沿革列 11/05。兩邊都稱上市，缺首次交易日或掛牌生效通知可區分。 [TWSE 個股頁](https://www.twse.com.tw/pdf/ch/1303_ch.pdf) · [年報](https://www.npc.com.tw/npcfile/public/report/year/20240702152139052.pdf) · [發行人簡介](https://www.npc.com.tw/j2npc/zhtw/CompanyProfile.jsp) | BLOCKED | 0／0 日 |
| 1449 佳和 | 1992/05/06／1992/03/12 | TWSE 個股頁列 05/06 上市；03/12 的 ISIN 起日缺少可辨識所指事件的原始公告或成交資料。 [TWSE 個股頁](https://www.twse.com.tw/pdf/ch/1449_ch.pdf) | PARTIAL | 0／0 日 |
| 2491 吉祥全 | 2001/09/19／2001/09/17 | 發行人簡介列 2000/02/21 上櫃、2001/09/19 開始上市，兩者均有明確市場定義。09/17 的 ISIN 日期仍缺事件主證。證交所查價端點拒絕歷史起始日以前的請求。 [發行人簡介](https://www.focl.com.tw/about.php) · [TWSE 個股頁](https://www.twse.com.tw/pdf/ch/2491_ch.pdf) | PARTIAL | 0／0 日 |
| 6133 金橋 | 2003/08/25／2003/08/15 | 同期 TWSE 年報與 Fact Book 支持 08/25 開始交易，發行人財報也列 08/25。ISIN 與現行 TWSE 個股頁列 08/15。缺可解釋欄位來源的通知。查價端點拒絕歷史起始日以前的請求。 [TWSE 年報](https://www.twse.com.tw/downloads/zh/about/company/Annual/92/025-031.pdf) · [Fact Book](https://www.twse.com.tw/downloads/zh/about/company/factbook_2004.pdf) · [TWSE 個股頁](https://wwwc.twse.com.tw/pdf/ch/6133_ch.pdf) | PARTIAL | 0／0 日 |

實跑封存資料的嚴格 252 交易日規則，將候選日期暫時帶入同一組行情及公司行動，對比 2026/11/09 至 11/20 的 10 個可計算交易日。全市場資格名單、調整後新低名單及原始與調整後家數均一致。最早回看日為 2025/10/22，四組原始與候選日期均在此之前。原始上市區間保留。 [量化輸出及輸入 SHA-256](listing_date_impact_20261123.json) · [原始 ISIN 與身分證據](incremental_listing_start_review_20261123.json)

```bash
python -m scripts.listing_date_impact checkpoint.json research/incremental_listing_start_review_20261123.json
```

## 11/23 公司行動阻擋清單

[封存來源、逐項 SHA-256 與重播](session_action_coverage_20261123.json)已驗證，增量回傳 `session action evidence is incomplete`。T48、A24 的公開產品頁提供規格與樣本，尚未取得 11/23 可合法留存、重播的實檔。本次沿用已確認的來源限制。

| 類別 | 生效日和證券範圍檢核 | 正控制及剩餘證據 |
|---|---|---|
| 除權息 | PARTIAL。前後交易日有效日可核。11/23 空回應沒有全量範圍聲明。 | 前後日行可命中。仍需 11/23 T48 計算結果及 A24 普通股檔與無事件範圍聲明。 |
| 減資 | PARTIAL。11/23 日表與多日窗相符。 | 1808 恢復交易日、參考價 36.25 元單例通過。仍需 A24 普通股減資檔及該日涵蓋聲明。 |
| 面額變更、分割、反分割 | BLOCKED。面額預告回傳窗外事件，未能建立當日上市普通股全量。 | 窗外資料可作負控制。尚無三類有效日正控制或當日無事件的完整聲明。 |
| 股份轉換、合併、換發新股 | BLOCKED。申報日、事實發生日與初次掛牌表不足以確認既有證券事件全量。 | T48 可協助上下市勾稽。仍需看得到生效交易日、舊新 ISIN、換股比例與市場範圍的公告清冊。 |

[供應商交付規格](SUPPLIER_DATA_REQUEST.md) · [可寄出的試用申請信](SUPPLIER_TRIAL_EMAIL_ZH_TW.md)
