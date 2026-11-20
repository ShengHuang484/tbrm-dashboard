# TBRM v1.0（GitHub Pages）

保留 v0.1 簡潔卡片，新增市場概況資料品質提示；Refresh 先更新加權指數，再讀取 GitHub Actions 官方快照。

## 上傳
將 `index.html` 覆蓋 GitHub 專案根目錄同名檔案。`scripts/update_snapshot.py` 和 `.github/workflows/update-market.yml` 可維持既有版本。

## 限制
- 官方快照中，上市個股漲跌家數僅在交易日一致且有效樣本充足時顯示；使用單日個股漲跌比例作為暫定廣度指標，尚非正式歷史 ADR。
- 櫃買漲跌幅僅在同日且辨識到明確百分比欄位時顯示。
- VIX、跌停家數、外資現貨與融資餘額變化仍未完成解析，顯示缺值。
- GitHub Pages 的 Refresh 不會立即觸發 GitHub Actions；它會讀取最新已發布快照，並嘗試直接下載 TWSE 指數。
- 未實測 iPhone Safari 及線上官方 API；分數門檻仍未回測驗證。
