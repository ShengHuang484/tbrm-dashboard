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

## 受控主封存比較與 18:00 操作

以下容量以首次驗收的 262 份約 2.8 GB 原始位元估算。費用不含網路、備份、管理時間及授權費。

| 選項 | 成本、容量及保存 | 資料權限與可靠性 |
|---|---|---|
| 本機受控磁碟 | 已有空間時新增儲存支出可為零。可保留至授權期限，另需約一份備份空間。 | 原檔留在本人控制設備。依賴設備 18:00 開機及網路，宜安排備份與雜湊抽查。 |
| 私有物件儲存 | 例如 Cloudflare R2 Standard 標價 US$0.015／GB-month，公開免費層含每月 10 GB-month。若整戶仍在額度內，2.8 GB 的儲存部分可為零。保存取決於生命週期與授權期限。 | 可由常在線執行器寫入，私有 bucket、最小權限、保留版本及限制讀取。使用前須確認第三方雲端受控保存權。 [R2 定價](https://developers.cloudflare.com/r2/pricing/) |
| 私有 GitHub repo | 現有方案未必增加席位費。約 2.8 GB 生資料會累積 Git 歷史與版本，還需確認方案的 Git LFS 或 Git 容量限制。Git 檔持久並可追版本，刪除舊授權檔時須一併考慮歷史。 | 私有 repo 仍由第三方託管。須限制成員並確認授權。排程跟預設分支及 runner 可用性有關。 [Git 檔案限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) |
| GitHub Actions artifact | 依方案的 artifact 用量計費。既有冒煙檔為 7 日，預設保存 90 日並受 repo 設定與到期刪除影響。 | 只能當短期留證，需在到期前移入授權許可的主封存。排程可能延遲，須監測漏跑。 [Artifact 保存](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts) |

待核准後採下列方式運作：

1. 台北交易日 18:00 由私有且常在線的執行環境啟動。用交易所交易日曆判斷預期開市日。若無當天觀察且日曆有疑義，發出未確認通知。
2. 以每天日期做單工鎖，先跑手動收檔命令。所有嘗試保留各自目錄。成功寫入後執行 `verify`，核對 SHA-256、當日行情與名冊日期、交易日及缺價來源。依授權備份，並對備份副本再執行一次 `verify`。
3. 針對暫時性下載失敗或行情／名冊延遲，可在 18:20、18:50 各補擷取一次。若最終仍缺來源、日期不符或 hash 校驗失敗，在 19:05 前以私有通知送出日期、缺失來源名稱與操作紀錄位置。通知只含診斷資訊。
4. 除權息空回應或公司行動範圍未確認會保留品質狀態。收檔作業不進入 checkpoint。首個即時盤後收檔與私有通知需要實際執行環境驗收。

建議先用已有的受控本機磁碟進行首次盤後驗收。若需要無人值守，再依保存授權選擇私有執行器與物件儲存。現階段排程與保存位置仍等待核准。
