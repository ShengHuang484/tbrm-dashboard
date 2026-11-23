# 52 週新低正式啟用檢查表

正式評分為 45/50，`score_eligible=false`。研究分支及草稿 PR #1 保留兩種 1312 情境。

| 項目 | 狀態 | 證據與驗收方法 | 尚缺資料／使用者介入 |
| --- | --- | --- | --- |
| 1312 跨事件外部個案 | PASS | [外部兩日收盤與顯示精度](1312_rights_basis.json)配對封存前後收盤，支持 13.20 元口徑。 | 此個案已驗收，無需介入。 |
| 988 筆和 10 日逐檔重播 | PARTIAL（內部） | [歷史重播](historical_listing_result.json)比對完整名單 SHA-256。11/20 嚴格 425／944，放寬 463／1,038。 | 完整外部市場資料仍待交付。 |
| 逐日歷史普通股、停復牌及公司行動 | PARTIAL（已知個案） | [歷史區間](historical_listing_evidence.json)及[缺收盤摘要](missing_close_summary.json)。39 個期內掛牌對上官方封存，5 個下市區間及 15 段停買已核對。244＋82 個缺收盤有公告或交易活動證據，638 個未知。 | 全期點時上市與承繼清冊、反分割與停止交易全量資料仍缺。若有授權清冊，可交付。 |
| 全市場獨立還原價 | BLOCKED | [供應商需求](SUPPLIER_DATA_REQUEST.md)與 [5 類抽樣事件](external_event_cases.json)。驗收會列出兩種 1312 口徑、樣本差異與 10 日逐檔市場差異。 | 需要合法匯出或授權，及調整方式原始文件。 |
| 正式口徑與啟用 | REVIEW | [1312 重播](1312_rights_scenario.json)顯示 425／424。覈對未決上市、價格與新低差異後確認。 | 需要使用者核准正式指標定義及是否啟用。 |

全期間 262 日已完成內部行情對重建區間檢查。官方掛牌與停買證據涵蓋已列個案。完整獨立母體、停復牌及還原行情均未取得。

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

取得供應商資料後，可加入 `--alternative-report alternate-ordinary.json --raw-history data/history/new_low_closes.json --event-cases research/external_event_cases.json`。替代報表以另一種 1312 口徑重播。跨事件未提供報價及未取樣類別會列出，兩種診斷輸出均維持研究旗標關閉。110 項本地測試通過。
