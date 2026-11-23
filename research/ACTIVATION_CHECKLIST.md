# 52 週新低正式啟用檢查表

正式評分為 45/50，`score_eligible=false`。研究分支及草稿 PR #1 保留兩種 1312 情境。

| 項目 | 狀態 | 證據與驗收條件 |
| --- | --- | --- |
| 1312 現金增資跨事件報酬 | PASS（僅 1312 跨事件個案） | 同一份 Goodinfo 日表的 6/10、6/11 及 0.10 元顯示步長，支持 13.20 元基準。見 [事件證據](1312_rights_basis.json)。 |
| 1312 指標定義 | REVIEW | TWSE 理論參考價 13.40 對應 425 檔，認購權取零 13.20 對應 424 檔。雙口徑可配置，102 項測試通過。採既有股東的未行權收盤連續性時，13.20 有外部個案支持；採交易所理論除權重現時使用 13.40。請確認正式定義及供應商口徑。 |
| 988 筆與 10 日逐檔重播 | PARTIAL（內部） | 封存原始月報、事件年月及逐日名單指紋可重播。11/20 嚴格 425／944，放寬 463／1,038。 |
| 原始行情與已知上市／下市區間 | PARTIAL（內部） | 重建名冊包含 5 檔已下市證券，39 個期內起點與官方封存逐筆符合。五段公告停買核對 175／964 個缺收盤配對，剩餘 789 個待查。101 項測試通過。見 [歷史區間](historical_listing_evidence.json)。 |
| 逐日歷史普通股母體和公司行動完整性 | BLOCKED | 驗收涵蓋全期的上市／轉板／下市／停復牌／代號承繼區間，以及有前收、參考價、生效日的減資、面額變更、分割、反分割及股份交換。公開個案仍不能認定完整。 |
| 全市場獨立還原價 | BLOCKED | 需以授權日線比較 10 天的普通股母體及逐檔新低，逐筆解釋缺價、取位和調整口徑差異。 |
| 正式啟用 | REVIEW | 前項完成後，由使用者確認指標定義、未決差異與是否啟用。 |

## 外部資料交付規格

資料狀態為官方封存已取得、個股外部還原樣本部分取得、全市場獨立授權匯出尚未取得。供應商可按下列欄位交付。

- **報價 CSV** 採 `date,code,adjusted_close`、UTF-8、ISO 日期、TWD、十進位原始精度。覆蓋 2025-10-22 至 2026-11-20 共 262 個交易日。每個目標日需含當日與前 252 個市場交易日。未成交或停牌缺價不補 0，也不沿用前收。
- **交易日曆 CSV** 採 `date`。說明市場休市、颱風補正及日期時區。
- **上市區間 CSV** 採 `code,listed_from,delisted_on`，下市日為排他邊界。需包含期內下市及重新上市。若代號重用，另附 ISIN 或供應商永續識別碼及承繼關係。
- **來源說明 JSON** 交付匯出日期、`provider`、`source_url`、`adjustment_method`、`data_origin=provider_adjusted_close`、`usage_basis`。另附幣別與小數位、除息／股票股利／有償現增／減資／分割／反分割及合併的調整規則。現增需說明認購價高於參考價的處理；股利需說明未取位或 TWSE 參考價取位。載明可使用、保留及公開衍生統計的授權範圍。
- TEJ 公開文件列有 TWN/APRCD1「上市櫃調整股價(日)-除權息調整」。本輪未取得授權匯出或確認歷史下市列、所有事件口徑及價格精度。若已有合法存取，可提供上述 CSV 與方法文件供逐筆驗收。[供應商文件](https://www.tejwin.com/insight/%E8%82%A1%E5%83%B9%E9%97%9C%E9%8D%B5%E5%8F%8D%E6%8C%87%E6%A8%99/)

## 核驗命令

先依封存工作流程取得 `adjusted.json`，再執行：

```sh
python -m scripts.historical_listing_replay data/history/new_low_closes.json adjusted.json \
  research/issuer_master_20261122.csv research/historical_listing_evidence.json \
  --strict-report > strict-ordinary.json
python -m scripts.new_low_baseline_import metadata.json quotes.csv calendar.csv \
  --listings listings.csv > baseline.json
python -m scripts.new_low_baseline strict-ordinary.json baseline.json > differences.json
```

覆核所有差異、缺價與不可比列，透過來源方法和樣本事件確認外部基準獨立性，並以所選口徑保存重播證據。

若要輸出現增認購權取零情境，在歷史重播命令加上 `--rights-basis zero-rights --rights-evidence research/1312_rights_basis.json`。

## 供應商交付自動驗收

增加 `currency=TWD`、`timezone=Asia/Taipei`、`price_decimal_places`、`exported_on`、`rights_basis` 與 `corporate_action_rules` 欄位。規則逐項覆蓋現金股利、股票股利、現增、減資、分割、反分割與合併。供應商應附來源方法與授權；格式檢查不替代對兩者的人工核驗。

```sh
python -m scripts.external_delivery_check strict-ordinary.json metadata.json quotes.csv calendar.csv listings.csv
python -m scripts.external_delivery_check research/examples/external_delivery/{report.json,metadata.json,quotes.csv,calendar.csv,listings.csv}
```

[合成範例](examples/external_delivery)僅展示欄位。驗收會比對雙邊完整交易日曆、報價精度、1312 情境、上市身分與逐檔資格／低點差異，另列未提供的上市歷史。105 項本地測試通過。使用者需提供合法供應商匯出與可使用範圍，或提供已授權來源的存取方式。
