# 臺灣上市普通股歷史還原行情資料需求

用途為驗證 52 週新低指標及公開彙總研究結果。請提供 **2025-10-22 至 2026-11-20** 臺灣證券交易所上市普通股（含創新板）的資料。範圍涵蓋期內下市、轉板及重新上市的證券。10 個研究日可各自回看 252 個市場交易日，整體研究日曆共 262 日。

| 檔案 | 必要欄位與定義 |
| --- | --- |
| 日線 `quotes.csv` | `date,code,adjusted_close`。TWD，採供應商輸出的十進位精度，日期以 Asia/Taipei 記錄，日期與代號唯一。缺有效收盤時留缺並提供狀態，不沿用前收或填零。 |
| 市場日曆 `calendar.csv` | `date`。依交易日排序、日期唯一，另提供休市與更正說明。 |
| 歷史掛牌 `listings.csv` | `code,listed_from,delisted_on,security_id`，下市日為排他界線。 `security_id` 採 ISIN 或供應商永續識別碼。簡版三欄格式只接受每個代號一段區間。另附具生效日的市場別、普通股身分、代號承繼及轉板資料。 |
| 交易狀態 | 代號或永續識別碼、開始日、恢復或結束日、事件類型、交易筆數或缺價原因、資料來源。請說明零成交及無有效收盤的定義。 |
| 公司行動 | 代號、永續識別碼、生效日、前收、參考價或係數、事件類型及來源。涵蓋現金與股票股利、有償現增、減資、分割、反分割、合併及股份承繼。 |
| 來源 `metadata.json` | 供應商、匯出日期、來源網址、幣別、時區、價格小數位、資料版本、調整規則、`rights_basis` 及授權範圍。 |

請說明調整價的原始報價及公司行動來源、運算方向、股利取位、同日多事件、換碼、下市和資料修正方式。1312 國喬於 2026-06-11 現增，請指明採 TWSE 理論參考價 13.40 元（`twse-reference`）或認購權取零 13.20 元（`zero-rights`），或另附供應商實際口徑。請提供可保存的匯出及版本或查詢方式，並註明行情是否可供專案維護者研究、保存與重播，以及是否允許公開衍生統計。原始行情可循授權限制私下交付。

驗收包含檔案雜湊、完整日曆、歷史掛牌／下市區間、缺價原因、五類跨事件樣本的還原比值，以及 10 個研究日的逐檔合格與新低差異。另需人工核對反分割、合併／承繼、原始來源獨立性及使用授權。供應商差異將逐筆列出並保留原始口徑。

有成對行情的相鄰市場交易日會按代號比較調整後收盤比值，保留供應商兩端各半個顯示單位的捨入範圍。代號跨上市區間時單獨列示。請附可重播的版本或修正紀錄以及調整基準日，以便區分取位差異、調整方式差異及行情更正。

若交付附有檔案校驗碼，請在來源 JSON 的 `file_sha256` 填入 `quotes`、`calendar`、`listings` 三個原始 CSV 的小寫 SHA-256。驗收工具會逐檔比對，並另外記錄收到的來源 JSON 雜湊。

[欄位範例](examples/external_delivery) · [跨事件驗收樣本](external_event_cases.json) · [啟用及驗收命令](ACTIVATION_CHECKLIST.md)

### 全套驗收交付

必備的六個 CSV 為 quotes、calendar、listings、roster、trading_status、events。逐日清冊使用 `date,code,security_id`，同一交易日的身分必須與四欄 `listings.csv` 一致。交易狀態使用 `date,code,reason,source_url`，只針對應在上市母體但沒有收盤的列。可用原因為 `announced_stop`、`company_action_stop`、`activity_without_close`、`zero_reported_activity`、`source_missing`、`unconfirmed`。事件使用 `date,code,event_type,successor_code,source_url`，僅合併與股份轉換填接續代號；同日多種事件分列。

來源 JSON 另附 `origin=external`、`upstream_source`、`usage_basis`、`usage_limits`、`adjustment_anchor_date` 與六檔原始 `bundle_sha256`。方法需明列 `face_value_change` 和 `share_conversion`，並覆蓋既有七類調整。若只能交付部分日期或部分證券，請標明限制。資料使用與來源獨立性須以授權及取樣文件人工確認。

以 `python -m scripts.external_delivery_bundle strict.json alternative.json raw-history.json event-cases.json local-gaps-full.json metadata.json supplier-directory/` 執行全套驗收。調整價倍數可能隨基準日整體縮放，逐日使用收盤比值和原始精度比較，保留個股跨上市區間及缺價原因供人工覆核。

### 取得前的確認項目

實測 FinMind 還原日線的已下市控制樣本 2867 回會員權限限制，TEJ APRCD1 回 API key 必填。若有既有授權，請依上述六檔規格提供 262 個交易日，先交付一包含 2867 最後交易日前後與 1312 現增日期的小樣，併附證券身分、公司行動、還原公式與原始報價上游。請說明是否可作市場級對照，並以書面列出可留存、內部使用及可公布統計的範圍。已授權樣本確認後，再進行全市場批次驗收。

驗收報告以 `intake_blockers` 列出缺資料情況，以 `comparison_review_counts` 列出需覆核的口徑或名單差異。檔案結構或合成測試通過後，來源獨立性及授權仍各自保留人工審查。

## 最小試用樣本

可先交付以下三組小樣，再確認全期授權。三組均須註明資料版本、產出時間（含時區）、上游原始來源、欄位定義、供應商自行執行的調整，以及各檔 SHA-256。請以書面說明內部研究、保存、重播與公開衍生統計的許可範圍。

| 樣本 | 最少交付 | 驗收重點 |
| --- | --- | --- |
| 2867 三商壽 | 2026-08-19 至 2026-09-01 的逐市場交易日身分與交易狀態。附 2867 與承接公司 2884 的永久識別碼、轉換事件、日期、換股條件，以及 2867 最後交易日的原始與還原收盤。 | 最後交易日、停止買賣及終止上市依據可重現。停買期間保留狀態，9/1 起 2867 排除，價格序列維持各自的證券身分。 |
| 1312 國喬 | 2026-06-10、06-11 的原始與還原收盤，以及 11/20 固定調整基準日。另附 05-27 與 11-20 還原收盤、現增認購價／配股率、調整因子與取位方式。 | 比較 13.40／13.20 和 13.20／13.20 兩種因子及跨日報酬。若只供一種口徑，仍可比對，但需說明如何處理價外認購權。 |
| 2026-11-23 TWSE 身分 | 截至台北收盤時的一般板與創新板全量普通股，提供 `date,code,security_id` UTF-8 CSV，另附市場別、證券類型、上市生效日、覆蓋與排除規則的欄位說明或附檔。 | 同源參考為 1,088 檔。逐筆核對代號與 ISIN，列出成員和識別碼差異，四位數 TDR 排除。用供應商自有永久識別碼時需附 ISIN 對照。 |

11/23 小樣可用以下命令比對。參考檔只表達當日身分。候選檔在來源與使用權審查前僅屬待驗證交付。

```bash
python -m scripts.new_low_session_probe 2026-11-23 checkpoint.json raw-directory/ --identity-retrieved-on 2026-11-23 --roster-reference-output roster-reference.json > probe-report.json
python -m scripts.historical_roster_check roster-reference.json --roster supplier-roster.csv --manifest supplier-roster-manifest.json
```

[TEJ 試用說明](https://api.tej.com.tw/documents.html)要求向供應商索取試用 API key，而且試用限指定表。其[目錄](https://api.tej.com.tw/databases.html)列有證券屬性與日調整股價，尚需供應商確認三組樣本是否都可匯出及其使用授權。[FinMind 調整日線](https://finmind.github.io/tutor/TaiwanMarket/Technical/)限指定會員，先前實際請求未取得資料。既有 Goodinfo 1312 顯示樣本可做個案對照，完整驗收另需原始精度及完整時間窗。三組小樣是來源核對的第一步，完整交付仍依本文件的 262 交易日六檔規格。

[Goodinfo 2867 還原價頁](https://goodinfo.tw/tw/ShowK_Chart.asp?CHT_CAT=DATE&PRICE_ADJ=T&STOCK_ID=2867)於 11/24 顯示查無相關資料。[公司轉換公告鏡像](https://goodinfo.tw/tw/StockAnnounceList.asp?END_DT=2026%2F8%2F17&START_DT=2026%2F7%2F18&STOCK_ID=2867)可驗下市個案，價格樣本仍待合法交付。

### 可直接交付的三組小樣驗收包

請提供一個目錄，內含下列四個檔案。可複製 [欄位、資料及授權範例](examples/supplier_sample/) 後替換內容。CSV 使用 UTF-8，欄名及欄位順序依例。日期為台北交易日，價格為 TWD 的一般交易收盤。價格缺值以空欄表示。原始價至少 2 位小數，調整價至少 4 位，最多 10 位；供應商須說明取位方法。

| 檔案 | 小樣必交範圍 |
|---|---|
| `lifecycle.csv` | 2867 的 08-19 最後交易、08-20 停止交易、09-01 終止上市，以及 2884 的 09-01 交易，共 4 個查核節點。09-01 的 2867 列明 2884 及每舊股 0.2596 新股。提供可核對的永久證券 ISIN。另附完整區間時，保留原檔並匯出這 4 列供小樣驗收。 |
| `rights.csv` | 1312 的 05-27、06-10、06-11、11-20。兩個序列錨定 11-20；僅於 06-11 前將 13.40 口徑乘上 13.40／13.20，13.20 口徑因子為 1。這些日期至錨點間的本地封存只有此一 1312 價格因子。 |
| `roster.csv` | 2026-11-23 的 1,088 個 TWSE 一般板及創新板普通股代號與 ISIN，須排除 TDR。以代號排序、LF 換行建立正規化比對雜湊。KY 等外國發行人的 ISIN 一併保留。若有差異，請另外提供市場別、證券種類、生效日或供應商公告。 |
| `manifest.json` | 三份交付原始位元各自的 SHA-256、來源與上游、取得版本、價格方法、固定錨點、幣別、供應商、授權參照，及研究、留存、重播權限。另附可供人工查閱的授權文件；公開衍生統計許可請在文件內明列。 |

在 repo 根目錄執行一鍵驗收。

```bash
python -m scripts.supplier_sample_check /path/to/delivery
```

- **PASS（exit 0）**範例輸出為 `{"intake_status":"PASS","coverage":"three_samples_only","license_and_independence_review":"REVIEW","score_eligible":false}`。可執行 `python -m unittest tests.test_supplier_sample_check.SupplierSampleTest.test_synthetic_pass_keeps_independence_and_scoring_unverified` 重現合成案例。
- **FAIL（exit 1）**可對 repo 內的欄位範例直接跑驗收。範例只有兩筆名冊，結果會報 `roster does not match the same-source reference count and identity digest`。原始位元雜湊不符、前後身分混接、停牌日填價或 1312 使用同一折算因子，也會明確拒絕。
- 小樣 PASS 表示檔案與本地研究對照相符。供應商上游獨立性、使用權及全歷史範圍須另行驗證。現況 **等待外部合法交付**。

### 11/23 公司行動生效清冊的指定交付

| 來源 | 請提供 2026-11-23 的項目 |
|---|---|
| [TWSE T48 除權息及上下市資訊檔](https://eshop.twse.com.tw/zh/product/detail/000000006e0bbe8d016f182105d90328) | 原始檔、產製日期及生效日與範圍聲明。依公開格式，資料區分 1 為除權息計算結果、2 為預告、3 為上市、4 為下市。計算結果依生效日比對，預告保留為獨立資料；上下市列的參考價欄為零。 |
| [TWSE A24 除權除息資訊](https://eshop.twse.com.tw/zh/product/detail/c96acc4e31d442eab373414c9f134844) | 普通股除權息及減資檔，附原始位元與公告及有效日欄位說明。普通股減資以恢復交易日比對，1808 是應命中的正控制。 |
| 交易所生效公告及可核對清冊 | 面額變更、分割、反分割、股份轉換、合併及換發新股。請包含代號／ISIN、有效交易日、舊新證券對照、換股條件及公告連結。若該日無某類生效事件，請明列所確認的證券與事件範圍。 |

上列檔案皆需附研究、留存及重播授權。T48 和 A24 的商品說明僅能確認欄位及產品涵蓋種類；仍須取得 11/23 實際檔案與交易所生效清冊。公開 [T48 格式檔](https://eshop.twse.com.tw/uploadFile/upload/000000006e0bbe8d016f3b0984a1038a.docx) SHA-256 為 `114335e5a51e7237cabcbfc1ec275b5193cdc2302fc0517a09f0e4d584b288d8`。
