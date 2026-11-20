# TBRM v0.9 GitHub Pages

維持 v0.1 簡潔介面。Refresh 仍從 TWSE FMTQIK 取得指數歷史，並嘗試讀取由 GitHub Actions 儲存的官方快照。**目前不會因為按下 Refresh 而立即啟動 GitHub Actions**。GitHub Actions 每個交易日台灣時間 17:15 排程執行（GitHub 可能延遲），也可在 Actions 頁手動執行。

## 安裝

將此資料夾內 `index.html`、`scripts/`、`.github/`、`README.md` 上傳到 repository 根目錄（保留資料夾路徑）。在 GitHub repository 的 Settings → Actions → General → Workflow permissions 設為 **Read and write permissions**，否則 workflow 無法提交快照。可至 Actions → Update official market snapshots → Run workflow 手動執行。完成後重新打開 Pages 網頁按 Refresh。

## 重要限制

- `data/` 的檔案僅在 GitHub Actions 成功下載後才會出現。沒有檔案時網頁會提示「官方快照尚未發布」，不是成功更新。
- 不同來源資料日期可能不一致，僅在可驗證同一交易日時才可參與計分。
- 目前自動補入：上市個股上漲/下跌家數（由 `STOCK_DAY_ALL` 逐檔漲跌點數推算，與交易所官方「普通股漲跌家數」口徑可能不同）；融資與櫃買資料只保留官方快照，不會擅自當作模型分數。
- 市場廣度得分的門檻是研究用暫定規則，不代表經歷史回測驗證。
- GitHub Pages 為靜態網站，不具備在按 Refresh 時執行伺服器端 Python 的能力；如需「按一下立即向所有交易所抓取」，須額外部署後端服務。
