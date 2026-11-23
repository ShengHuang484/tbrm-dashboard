# 休市後的個股交易日與價格證據

原始除權息日期仍保留在事件來源。以下逐檔對照只供研究。前收取自
`data/history/new_low_closes.json` 的復市前一個 TWSE 交易日。券商欄的前收對照值
採用該頁的填息價，這是純現金除息的交叉檢查，混合除權息需另核對股數比率。
下表的價格佐證也不能建立整段期間的公司行動完整性。

| 代號 | 原日期 → 復市候選日 | 本地前收 | 外部前收 / 參考價 | TWT49U 參考價 | 逐筆證據 |
| --- | --- | ---: | --- | --- |
| 2008 | 07-10 → 07-13 | 29.85 | 29.85 / 28.85 | 28.85 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=2008) 列復市日 |
| 2610 | 07-10 → 07-13 | 21.40 | 21.40 / 20.59 | 20.58 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=2610) 列復市日 |
| 2891 | 07-10 → 07-13 | 69.90 | 69.90 / 67.40 | 67.39 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=2891) 列復市日 |
| 3034 | 07-10 → 07-13 | 542.00 | 542.00 / 519.00 | 519.00 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=3034) 列復市日 |
| 3055 | 07-10 → 07-13 | 158.00 | 158.00 / 157.50 | 157.50 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=3055) 與[國泰](https://djinfo.cathaysec.com.tw/z/zc/zci/zci.djhtm?A=3055) 均列復市日 |
| 4968 | 07-10 → 07-13 | 111.50 | 111.50 / 109.90（原日期） | 109.90 | [Stockapy](https://stockapy.com/stock/4968/) 日期吻合，但列出的事件金額 3.177 與[公司公告](https://goodinfo.tw/tw/StockAnnounceDetail.asp?CLAIM_TIME=2026%2F06%2F11+13%3A53%3A29&STOCK_ID=4968&SUBJECT=%E5%85%AC%E5%91%8A%E6%9C%AC%E5%85%AC%E5%8F%B8%E8%A8%82%E5%AE%9A%E7%8F%BE%E9%87%91%E8%82%A1%E5%88%A9%E9%99%A4%E6%81%AF%E5%9F%BA%E6%BA%96%E6%97%A5) 的 1.60 不同。[ToAlpha](https://toalpha.tw/stock/4968/dividend) 的價格沿用原日期 |
| 5519 | 07-10 → 07-13 | 34.45 | 32.96 / 29.66 | 29.66 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=5519) 列復市日。另見 [Goodinfo](https://goodinfo.tw/tw/StockDividendSchedule.asp?STOCK_ID=5519) 現金 3.30、股票股利 0.50，以及 [Yahoo 財經](https://hk.finance.yahoo.com/quote/5519.TW/history/) 當日股數比 1.05，原始前收需先確認價格基準 |
| 6477 | 07-10 → 07-13 | 39.85 | 39.85 / 39.50 | 39.50 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=6477) 列復市日 |
| 2028 | 10-23 → 10-27 | 16.55 | 16.55 / 16.35 | 16.35 | [凱基](https://superpy.kgieworld.com.tw/kgipythonapi/stockInfo/finance/exDividend?stockCode=2028) 列復市日 |
| 6931 | 10-23 → 10-27 | 37.50 | 37.50 / 待核 | 37.38 | [Yahoo 股市](https://tw.stock.yahoo.com/quote/6931.TW/profile) 顯示 10-27。[公司原公告](https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=9d841b11-cc9e-4e75-9ef3-09646d04d2d1) 的 10-27 是最後過戶日，需以實際生效紀錄、正式參考價再核對 |

[證交所原始月報及逐筆審查佇列](https://github.com/ShengHuang484/tbrm-dashboard/actions/runs/45059710691)
的 10 筆官方前收全數吻合本地復市前收。7 筆純現金事件有券商實際復市日期及價格欄位，
其中 5 筆參考價精確相同，2610、2891 與券商各差 0.01 元。分別應核對精確息值
0.814457、2.500239 和各來源的截位規則，係數保留官方參考價與開盤競價基準的區別。

5519 的官方原始前收為 34.45，參考價 29.66。用公司股利資訊重建，
(34.45 − 3.30) / 1.05 約為 29.66667，截至小數第二位得到 29.66。
凱基的 32.96 為填息價，未能作為原始前收。6931 的官方原始參考價 37.38
與 37.50 − 0.12 一致，[外部報導](https://tw.stock.yahoo.com/news/%E5%8F%B0%E5%8C%97%E8%82%A1%E5%8C%AF%E4%BC%91%E5%B8%82%EF%BC%81-%E8%96%94%E7%90%B5%E9%A2%B1%E9%A2%A8%E5%81%9C%E7%8F%AD-4%E6%AA%94%E5%80%8B%E8%82%A1%E9%99%A4%E6%AC%8A%E6%81%AF%E5%BB%B6%E5%BE%8C%E5%88%B0%E4%B8%8B%E5%91%A8%E4%BA%8C-122538662.html)也列出威致及青松健康順延。

目前 10 筆都有逐檔的復市日支持資料。官方月報仍標示休市日，日期修訂須有
可重現的正式生效紀錄。係數價格來源差異及 4968 的外部金額衝突也保留待查。
