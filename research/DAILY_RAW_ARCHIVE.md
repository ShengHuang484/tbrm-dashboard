# 每日原始資料封存

封存程序只讀公開來源，輸出一個新的日期／嘗試目錄。輸出含原始回應、來源網址、取得日期、原始位元 SHA-256 及可觀察的回應日期或範圍。此入口不接受 checkpoint，固定輸出 `action_coverage_reviewed=false`、`score_eligible=false`，後續日可獨立封存，11/23 仍是增量重播的下一個待驗收交易日。

## 手動收檔

使用授權允許的受控目錄。在台北當天 16:00 後執行。16:00 為手動收檔門檻，若來源尚未更新，可晚些再收一次。每次嘗試分開保存。完整 ISIN 頁和兩個分類端點須一起核對；過日取得的現行名冊不能追認為歷史當日名冊。

```bash
session=$(TZ=Asia/Taipei date +%F)
attempt=$(python -m scripts.new_low_raw_archive collect "$session" /path/to/private/raw-archive)
python -m scripts.new_low_raw_archive verify "$attempt"
```

| 收檔 | 來源與驗收界線 |
|---|---|
| 行情 | TWSE MI_INDEX 指定交易日。核對日期與收盤表欄位，保留缺收盤列。 |
| 普通股名冊 | TWSE ISIN 全頁、創新板及 TDR 分類。核對當日全頁日期與分類內容，分列普通股及行情中的 TDR。 |
| 交易日 | TWSE FMTQIK 當月市場成交。日期出現在表中才標記 observed_open；當日未出現時維持 not_yet_observed。 |
| 公司行動 | 除權息、減資、面額預告、新上市清單與 TWSE 公開重大訊息。日期欄不符或空回應維持未確認範圍。已保存的公司行動來源仍需另經全量驗收。 |
| 缺價 | 對當日名冊內缺收盤或缺行情列的代號逐一保存 STOCK_DAY 原始月報。當日列缺失、停牌或無收盤等資訊都保留證據和可辨識狀態。 |

若要重驗舊檔，先準備來源清單 JSON，每個來源鍵對應原先記錄的 `url` 和 `sha256`，個別檔日期不同時另填 `source_capture_date`。雜湊不符的檔案會標記 unavailable。匯入日期應取原始收檔紀錄。

```bash
python -m scripts.new_low_raw_archive import 2026-11-23 /path/to/private/raw-archive raw-directory/ \
  --source-capture-date 2026-11-23 --source-manifest source-manifest.json
```

11/23 手動驗收用既有官方原始位元和當時保存的雜湊。9 份檔案成功匯入，行情四碼代號 1,092、普通股 1,088、行情內 TDR 4。1538 比對為有成交活動但無收盤。除權息空回應維持範圍未確認，減資日期吻合，面額與新上市原檔缺少可對應的同日來源雜湊，列 unavailable。manifest SHA-256 為 `118f855d894ff5742d8b0ccfa39378e2b34f7057706391c6efa25adbf31b936c`。校驗在原始位元遭改動時會拒絕。 [驗收 manifest](daily_raw_archive_20261123_manifest.json)

這次的原始位元約 10.8 MB。以同樣大小保留 262 次收檔，未壓縮約 2.8 GB；多次重試或較大的 ISIN 頁會增加用量。

## 保存與待核准排程

- 優先使用授權允許的受控持久磁碟。暫存工作區與 GitHub artifact 都有存續限制。既有 TWSE 冒煙 workflow 明列 7 天。GitHub 文件的公開 repo 設定上限為 90 天，仍需檢查 repository 實際設定、授權與存取對象。 [GitHub 保存設定](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
- 11/23 現行驗收只在工作區留存原始檔。正式保存地點、期間及傳輸範圍應依 TWSE、ISIN 與供應商的書面使用權決定。公開規格與可下載回應無法單獨證明可再散布。
- 待核准的排程方案是在可保有授權檔的私有執行環境，以台北交易日 18:00 執行同一手動命令；先由操作人確認保存路徑與權限，盤後未齊時保留當次證據再重試。GitHub schedule 依賴預設分支，研究分支目前不加排程或 artifact 上傳。 [GitHub 觸發條件](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)
