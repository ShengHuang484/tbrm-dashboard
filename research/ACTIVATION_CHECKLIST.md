# 52 週新低正式啟用檢查表

正式評分為 45/50，`score_eligible=false`。草稿 PR #1 保留兩種 1312 情境，所有工具只產生研究輸出。

| 驗收條件 | 狀態 | 目前證據及自動驗收 | 尚缺資料、下一步及使用者介入 |
| --- | --- | --- | --- |
| 內部歷史與逐檔重播 | PASS | 固定封存 Actions 核對 262 日、普通股 988 筆因子、10 日名單雜湊及 964 個缺價歸因。11/20 嚴格合格 944 檔。 | 續留封存與 CI 結果。無需介入。 |
| 官方資料個案 | PARTIAL | [歷史區間](historical_listing_evidence.json)及[封存結果](historical_listing_result.json)對上 39 筆期內掛牌、5 筆退出和 31 段停買。公開暫停交易報表未涵蓋 8105、1435 控制案例。 | 取得全期間轉板、停復牌、反分割與承繼清冊後逐筆檢查。已有合法授權者可交付。 |
| 外部個股 1312 | PASS | [個案資料](1312_rights_basis.json)中跨事件還原報酬支持 13.20 元。以顯示區間核對前後收盤比值。 | 個股證據已驗收。正式定義或其他公司請在相應驗收項目處理。 |
| 全市場歷史母體獨立驗證 | BLOCKED | `scripts.historical_roster_check` 輸出逐日成員、證券身分、缺漏區間與覆蓋，獨立觀測目前 0／262。 | 以合法 262 日普通股清冊、永久識別碼及市場別跑批次差異。需資料授權與來源覆核。 |
| 全市場還原行情獨立驗證 | BLOCKED | `scripts.external_delivery_bundle` 核對六檔 SHA-256、日曆、調整基準日、停牌、事件、逐日比值與 10 日兩口徑低點。合併、反分割及 1312 合成驗收已通過。 | [供應商需求](SUPPLIER_DATA_REQUEST.md)列明交付。取得後核對上游來源、精度、公司行動及使用權，再跑全市場。需合法授權。 |
| 研究用每日增量 | PARTIAL | 262 日 checkpoint 由 Actions 重建。11/23 證交所原始行情獨立於本地封存取得，已核日期；合成情境驗證跨年、休市、颱風停市、延遲及歷史修正。 | 補齊同日逐日名冊、事件、日曆與缺價證據，完成實際增量驗收。尚無排程或正式計分串接。 |
| 正式口徑與最後 5 分 | REVIEW | [批次掃描](rights_basis_scan.json)有 61 筆普通股候選參考價差，1312 是唯一上調者。11/20 的 425／424 差異只來自 1312。 | 確認完整外部差異後，由使用者核准價外認購權的正式處理及啟用。 |

證交所[每日證券市場概況資訊](https://eshop.twse.com.tw/zh/product/detail/000000006f6a5e3401702de5988d004b)商品說明列出證券別、代碼、ISIN 與上市日，適合作為後續官方歷史核對候選。未購買或取得該份歷史資料，且其來源與本地 TWSE 證據同源。供應商仍須聲明上游、計算方法與授權。

## 執行順序

1. 由封存 Actions 的固定來源重建 `strict.json`。歷史上市重播加入 `--rights-basis zero-rights --rights-evidence research/1312_rights_basis.json` 取得替代基準。
2. 執行 `python -m scripts.historical_roster_check strict.json --roster roster.csv --manifest roster-manifest.json`。來源 JSON 提供 `origin`、`source_url`、`retrieved_on`、`covered_dates`、`sha256`，外部來源另附 `upstream_source` 與 `usage_basis`。
3. 依供應商規格執行 `scripts.external_delivery_bundle`，人工覆核價格、上市、事件、停牌及無法比較的列，並核對授權。
4. 經人工核准後，才評估正式連線及啟用。研究基準二選一的建議是先向供應商驗證價外現增認購權與同期配股規則。對 1312，現有外部樣本支持 13.20；保留官方 13.40 作對照。

## 研究用增量執行

- `python -m scripts.new_low_incremental seed raw-history.json strict.json local-gaps-full.json > checkpoint.json`
- `python -m scripts.new_low_incremental fetch-quote YYYY-MM-DD input/quotes.json` 下載並保存有日期驗證的原始行情。
- `python -m scripts.new_low_incremental replay checkpoint.json plan.json input/ > updated-research.json`。每次只追加一個已證實交易日，保留前 252 日所需資料。重複、漏日或待發布都中止，休市僅輸出休市診斷。
- `plan.json` 包含 `mode`（`append` 或 `correction`）、`origin`（`twse` 或 `synthetic`）、`as_of`、`session`、`checkpoint_sha256`、`sources`（每份 `source_url` 與 `sha256`）。歷史修正另需 `--allow-correction` 和 `revision_note`；歷史日曆修訂或多日補資料應逐日重播或重建封存。
- `calendar.json` 每曆日列 `date,state,reason`。正常交易另需四檔：原始 `quotes.json`、`listings.json`（`date,intervals,excluded_codes`）、`actions.json`（`date,coverage_reviewed,events`）和 `gaps.json`（`date,reasons`）。名冊需說明官方四位數代號的所有非普通股排除，事件需核來源與日別，缺價需逐檔證據。新 checkpoint 位於輸出 JSON 的 `checkpoint` 欄位。

## 封存持續性

研究 workflow 以 PR head 為準，固定封存以原始 ZIP 雜湊驗收。若 GitHub artifact 到期，研究重播會停止，需從獲准保留的副本恢復相同雜湊。

## 歷史母體來源實查

[TWSE／TPEx／政府開放平臺與 FinMind 查詢證據](historical_source_probe_20261123.json)保留端點、雜湊、查得日期與適用範圍。免費來源可核個案或當期快照。歷史獨立母體仍為 **BLOCKED，0／262**。

## 11/23 真實增量

[實查與守門輸出](incremental_acceptance_20261123.json)為 **BLOCKED**。日曆、官方行情、1,088 檔普通股 ISIN、4 筆 TDR 排除、1538 缺價及 1808 減資基準已核對。名冊為同源當日交叉核對，完整事件與 15 筆歷史起日差仍須覆核。可用 `python -m scripts.new_low_session_probe 2026-11-23 checkpoint.json raw-directory/ --identity-retrieved-on 2026-11-23` 重播已保存的原始輸入。檔名為報告 `sources` 內各鍵加 `.raw`，每份位元以其雜湊核對。

## 獨立還原日線存取

[FinMind／TEJ 實際回應](supplier_access_probe_20261123.json)顯示會員或 API key 阻擋，現有合法全市場交付為零。仍為 **BLOCKED**。取得既有授權後先核對 2867 下市及 1312 現增的小樣，再跑 [六檔交付驗收](SUPPLIER_DATA_REQUEST.md)。
