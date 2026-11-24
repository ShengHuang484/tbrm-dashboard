# 外部資料取得方案

查核日為 2026-11-24（台北）。下列價格為產品頁公開標示的新台幣價格。試用個案與完整交付的權限需各自確認。A、B 交付可平行，欄位、雜湊及命令見[交付規格](SUPPLIER_DATA_REQUEST.md)。

| 提供方 | 官方確認的產品、申請方式及公開費用 | 本案仍待回覆 |
|---|---|---|
| TWSE | **A**：T48 除權息及上下市資訊檔，公開格式範例，內部使用 NT$5,000／月、外部 NT$10,000／月。A24 除權除息資訊含普通股減資與恢復日，內部 NT$5,000／年、外部 NT$10,000／年。**B 的母體候選**：TRANISIN 每日證券市場概況，含市場、證券類型、ISIN 與上市日，內部 NT$5,000／月、外部 NT$10,000／月。同日檔非還原行情。內部方案限制對外公開。產品頁是訂購入口，亦可按官方聯絡資訊詢問歷史試用。 [T48](https://eshop.twse.com.tw/zh/product/detail/000000006e0bbe8d016f182105d90328) · [A24](https://eshop.twse.com.tw/zh/product/detail/c96acc4e31d442eab373414c9f134844) · [TRANISIN](https://eshop.twse.com.tw/zh/product/detail/000000006f6a5e3401702de5988d004b) | 有無免付費的 11/23 實檔與其餘生效事件的範圍聲明。確認 T48／A24 加上其他生效清冊是否覆蓋 A 八類。TRANISIN 雖提供逐日證券身分欄，仍需確認歷史下市日起落及 262 日成員完整性。TWSE 同源資料只能核對母體，不能獨力滿足 B 的獨立驗證。書面確認授權環境、離線留存期限及跨日重播。 |
| TEJ | **B 優先詢問**：TWN/APRCD1 是日調整股價資料，官方教學有還原價資料例。官方提供免費試用金鑰申請，須註冊並限試用表及額度。公開文件未列足以涵蓋本案的整包價格。 [產品目錄](https://api.tej.com.tw/databases.html) · [免費試用申請](https://api.tej.com.tw/trial.html) · [API 規格](https://api.tej.com.tw/documents.html) | 試用能否取 2867 下市前、2884 承繼、1312 雙口徑與歷史逐日母體。確認永久識別碼、262 日範圍、股利及資本事件因子、逐筆調整方法、上游獨立性，以及試用結束後留存／重播與公開彙總權限。整包需詢價。 |
| FinMind | **B 價格樣本候選**：TaiwanStockPriceAdj 限 Backer 或 Sponsor 等適用會員，技術文件說明回溯調整與基準日。免費會員不含該資料表。Backer NT$699／月或 NT$5,499／年，Sponsor NT$999／月或 NT$8,888／年，均標示非商業。Sponsor Pro NT$3,330／月或 NT$29,620／年。官方授權要求依上游確認再散布，方案權限不足以推得可把原始檔上傳公開 repo。 [方案價格](https://finmind.github.io/Pricing/) · [資料表規格](https://finmind.github.io/tutor/TaiwanMarket/Technical/#taiwanstockpriceadj) · [資料授權](https://finmind.github.io/Disclaimer/) | 有無免費授權抽樣、是否涵蓋 2867 下市及 1312 指定日期。TaiwanStockInfo 的公開規格未證明具 262 日逐日有效普通股母體及永久識別碼，亦未證明可滿足獨立上游要求。需取得試用後受控留存與重播的書面確認。 |
| CMoney | **B 備援詢價**：官方數據貓頭鷹提供金融 API，法人資料產品另列每日價格及還原行情。可循官方 API 產品頁聯繫。未核實涵蓋本案的公開費用或免費資格。 [官方 API 產品](https://cmoney.com.tw/product/api) | 確認是否可供 2867 歷史下市、262 日逐日名冊及永久識別碼、雙口徑與調整方法，以及留存重播等授權範圍。 |

## 最低成本的可行順序

1. 先向 TWSE 索取 A 的同日試用與全量聲明，同時向 TEJ 申請 B 的三組小樣。若已有授權或兩方核准免費試用，新增採購費可為 NT$0，仍須確認是否涵蓋全量。
2. 若 A 需採購，T48 一個月加 A24 一年按公開內部價的起始合計為 NT$10,000。此金額只涵蓋兩個產品，其餘公告清冊及必要授權項目需另確認。若供應商已有兩檔合法轉授權，可索取同日組合報價。
3. B 先拿 TEJ 或 CMoney 全包實際報價及範圍承諾。FinMind Backer 的 NT$699 是還原行情層級的列價，逐日歷史母體及獨立性尚待確認。TWSE 的 TRANISIN 可當官方對照。此階段沒有已證實滿足 A+B 所有條件的最低總價。

可用[兩封繁體中文詢問信](SUPPLIER_TRIAL_EMAIL_ZH_TW.md)分別索取。未收到授權資料以前，A、B 維持 WAITING_FOR_EXTERNAL_DATA；已確認受限的 API 不再重試。
