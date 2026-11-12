# 台股數字核對

看到台股貼文後，點開小工具即可對照三大法人、融資、融券與大盤數字。資料範圍是 **上市集中市場**，Python 實作，本機 SQLite 儲存。

直接下載證交所網站的公開 CSV，不需要金融服務帳號、API key 或付費 API。下載仍需要網路；已有的紀錄可離線查看。這是盤後資料，不是即時行情。

[完整視窗預覽](docs/screenshots/nord-overview.png) · [精簡視窗預覽](docs/screenshots/nord-compact.png)

## 開啟小工具

首次執行（以下以 2026/11/1 為起始日，可自行調整；本機資料庫不隨 repository 提供）：

```bash
git clone https://github.com/jason9075/stock-report.git
cd stock-report
uv sync --extra gui
uv run stock-report sync --start 2026-11-01
uv run stock-report widget --compact
```

之後可在專案目錄執行 `./scripts/widget.sh`。安裝下方的桌面捷徑後，也能在 Ubuntu 應用程式選單搜尋「台股數字核對」。

也可不使用 uv：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[gui]'
.venv/bin/python -m stock_report widget --compact
```

- **Nord 配色與分區**：以法人合計為主數字，下列外資、投信、自營商；另一區列出融資券餘額、當日增減及前日餘額。
- **數字層次**：以億元顯示主要金額；完整元數平時隱藏，滑鼠停留於金額時顯示。
- **日期導覽**：置中的日期選單，左／右按鈕切換前／後一個交易日；也能點歷史表格中的日期。
- **精簡／完整視窗**：精簡模式約 440 × 470，保留日期、法人金額、融資券餘額與增減，大盤改為單行摘要；完整數值可停留查看。「展開」可查看前日餘額、說明與歷史；📍／📌 切換置頂。
- **歷史數據／變化趨勢**：歷史表格預設以億元顯示，可切換完整元數；趨勢圖獨立成頁，不壓縮主要資訊。圖上標示刻度，停留可看逐日完整值。
- **完整報告與來源**：法人買進／賣出、融資券明細、每日變化、官方 CSV 連結與擷取時間。
- **匯出報告**：把所選日期與之前的紀錄輸出 HTML 或 Markdown。
- **系統匣**：點圖示開啟／隱藏；右鍵可查看最新摘要、更新或結束程式。重複啟動捷徑會叫出原視窗。
- **背景更新**：啟動後與執行中每 30 分鐘更新。關閉視窗會縮到系統匣；在右鍵選單選「結束」才會停止。

GNOME 桌面需要支援 AppIndicator 的擴充套件才能顯示系統匣。若環境不支援系統匣，仍可使用小視窗與工作列；此時關閉視窗便會結束程式。

安裝應用程式選單捷徑（不會加入開機自啟）：

```bash
uv run stock-report desktop-install
```

## 每日下載與報告指令

下載器只有 Python 標準函式庫依賴，沒有桌面環境也能使用：

```bash
# 第一次指定起始日；此設定寫入 SQLite，往後自動沿用
python3 -m stock_report sync --start 2026-11-01

# 日常更新：補漏並重抓最近三個交易日，接受官方調帳
python3 -m stock_report sync

# 重抓完整期間
python3 -m stock_report sync --refresh

# 終端機報告
python3 -m stock_report report

# 匯出離線報告
python3 -m stock_report report --output reports/latest.html
python3 -m stock_report report --output reports/latest.md

# 查看截至某日最近一個交易日
python3 -m stock_report report --date 2026-11-06

# 取得所有日期的原始數字 JSON（不使用億元縮寫）
python3 -m stock_report report --json

# 使用另一份資料庫；全域參數須放在子指令之前
python3 -m stock_report --db /tmp/tw-stocks.sqlite3 sync --start 2026-11-01
```

首次未指定 `--start` 時，採最近一次 11/1。例如 2026/11 預設 2026/11/1，2027/1 仍是 2026/11/1。日期以 Asia/Taipei 為準。

每月市場報表決定交易日，休市日不會當成「買賣超為零」。法人與融資券各自下載、儲存；部分尚未公布或失敗時會顯示缺漏，保留既有資料。下載失敗會重試，並以非零結束碼回報真正的錯誤。

## 數字口徑

| 項目 | 來源／單位 |
| --- | --- |
| 外資及陸資 | BFI82U，不含外資自營商，金額元 |
| 投信 | BFI82U，金額元 |
| 自營商 | 自行買賣＋避險；外資自營商已包含，不再重複加總 |
| 融資金額 | MI_MARGN，來源仟元，入庫換算成元 |
| 融資／融券數量 | MI_MARGN 官方「交易單位」，一般股票為張 |
| 每日融資券增減 | **同份報表今日餘額－前日餘額**，採用官方修正後前日餘額 |
| 大盤指數、成交額 | FMTQIK；指數漲跌幅由收盤指數與漲跌點數計算 |

主畫面以億元呈現主要金額（1 億＝100,000,000 元），完整元數改由滑鼠停留時顯示；歷史表格預設億元，可切換完整元數。完整數字直接由入庫整數格式化，不經浮點縮放。正數為買超／增加，負數為賣超／減少；Nord 紅／綠輔助辨識，文字同時標明買超或賣超。每份報表驗證日期、必要欄位與法人買賣合計，來源格式異常時不覆寫既有資料。

融券不是借券賣出，也不是期貨空單。這個版本沒有上櫃、借券或期貨資料；也不從總融資餘額推估個人損益、維持率或買賣建議。報告只列可計算的變化與比較。

官方對融資券的說明指出，資料在盤後彙整，今日餘額可能於次日調帳；以前日餘額為準、今日餘額為輔助。資料日與擷取時間都會保留，重抓可取得後續更正。

## 本機資料

預設資料庫：`data/stocks.sqlite3`。匯出範例：`reports/latest.html`、`reports/latest.md`。這些資料與 `.venv` 不納入版本控制。

SQLite 內容：

- `snapshots`：交易日＋資料種類為唯一鍵，`payload` 存原始數值 JSON，另存官方網址與擷取時間。
- `downloads`：留存經驗證的 CSV 文字，方便對帳；重抓會更新同一天／同月的版本。
- `settings`：起始日期設定。

可直接用 SQLite 查詢，例如：

```sql
SELECT date,
       json_extract(payload, '$.foreign_net') / 100000000.0 AS foreign_net_yi
FROM snapshots
WHERE source = 'institutions'
ORDER BY date;
```

## 驗證

```bash
python3 -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen uv run stock-report widget --screenshot /tmp/stock-report.png
```

測試使用 `tests/fixtures/` 的 2026/11/11 官方 CSV 節錄，不會連線。涵蓋金額與單位換算、日期錯誤、買賣對帳、部分失敗、缺漏補抓、重複下載不重複入庫、報告與日期篩選。

官方資料頁：

- [三大法人買賣金額統計表](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html)
- [信用交易統計](https://www.twse.com.tw/exchangeReport/MI_MARGN?response=html&selectType=MS)
- [市場成交資訊](https://www.twse.com.tw/exchangeReport/FMTQIK?response=html&date=20261101)
