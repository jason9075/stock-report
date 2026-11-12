from __future__ import annotations

import csv
import io
import re
import sqlite3
import time
import urllib.request
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "stocks.sqlite3"
SOURCES = {
    "market": "https://www.twse.com.tw/exchangeReport/FMTQIK?response=csv&date={date}",
    "institutions": "https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate={date}&type=day",
    "margin": "https://www.twse.com.tw/exchangeReport/MI_MARGN?response=csv&date={date}&selectType=MS",
}


def today():
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def default_start():
    # 最近一次 11/1；隔年一月開啟仍能延續上一年資料。
    now = today()
    return date(now.year if now.month >= 11 else now.year - 1, 11, 1)


class DataError(ValueError):
    pass


def number(value):
    try:
        return Decimal(value.replace(",", "").replace(" ", "").replace("\u3000", ""))
    except InvalidOperation as exc:
        raise DataError(f"無法辨識數字：{value!r}") from exc


def integer(value):
    n = number(value)
    if n != n.to_integral_value():
        raise DataError(f"預期整數：{value!r}")
    return int(n)


def decode_csv(raw):
    for encoding in ("utf-8-sig", "cp950"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise DataError("CSV 編碼無法辨識")


def rows_of(text):
    if "<html" in text.lower() or "<!doctype" in text.lower():
        raise DataError("來源回傳網頁而非 CSV，可能暫時無法下載")
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text)) if row]


def verify_date(text, day):
    match = re.search(r"(\d{2,4})年(\d{1,2})月(\d{1,2})日", text)
    if not match:
        raise DataError("報表缺少日期")
    y, m, d = map(int, match.groups())
    if date(y + 1911 if y < 1911 else y, m, d) != day:
        raise DataError(f"來源日期與要求的 {day} 不符")


def parse_institutions(text, day):
    rows = rows_of(text)
    if not text.strip():
        return None
    verify_date(text, day)
    result = {}
    for row in rows:
        if len(row) < 4:
            continue
        name = row[0].replace(" ", "")
        if name.startswith("外資及陸資"):
            key = "foreign"
        elif name == "投信":
            key = "trust"
        elif name.startswith("自營商(自行"):
            key = "dealer_self"
        elif name.startswith("自營商(避險"):
            key = "dealer_hedge"
        elif name == "合計":
            key = "total"
        else:
            continue  # 外資自營商已計入自營商，不重複加總。
        buy, sell, net = map(integer, row[1:4])
        if buy - sell != net:
            raise DataError(f"{name} 買賣金額無法對帳")
        result.update({f"{key}_buy": buy, f"{key}_sell": sell, f"{key}_net": net})
    if len(result) != 15:
        raise DataError("法人報表欄位不完整")
    for suffix in ("buy", "sell", "net"):
        result[f"dealer_{suffix}"] = result[f"dealer_self_{suffix}"] + result[f"dealer_hedge_{suffix}"]
        if sum(result[f"{k}_{suffix}"] for k in ("foreign", "trust", "dealer")) != result[f"total_{suffix}"]:
            raise DataError("三大法人合計無法對帳")
    return result


def parse_margin(text, day):
    rows = rows_of(text)
    if not text.strip():
        return None
    verify_date(text, day)
    result = {}
    for row in rows:
        if len(row) < 6:
            continue
        name = row[0]
        key = "financing" if name.startswith("融資金額") else "short" if name.startswith("融券(") else "financing_lots" if name.startswith("融資(") else None
        if key:
            values = list(map(integer, row[1:6]))
            # 融資金額來源單位仟元，入庫統一為元；交易單位照原報表。
            factor = 1000 if key == "financing" else 1
            for field, value in zip(("buy", "sell", "repay", "previous", "balance"), values):
                result[f"{key}_{field}"] = value * factor
    if len(result) != 15:
        raise DataError("融資券報表欄位不完整")
    return result


def parse_market(text, month):
    rows = rows_of(text)
    result = []
    for row in rows:
        if not row or not re.fullmatch(r"\d{2,4}/\d{2}/\d{2}", row[0]):
            continue
        if len(row) < 6:
            raise DataError("市場報表欄位不完整")
        y, m, d = map(int, row[0].split("/"))
        day = date(y + 1911 if y < 1911 else y, m, d)
        if (day.year, day.month) != (month.year, month.month):
            raise DataError("市場報表月份不符")
        close, change = map(number, row[4:6])
        result.append({"date": day.isoformat(), "turnover": integer(row[2]), "close": float(close),
                       "index_change": float(change), "index_pct": float(change / (close - change) * 100)})
    if text.strip() and not result:
        raise DataError("市場報表無可辨識的交易資料")
    return result


def connect(path=DEFAULT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript('''
    CREATE TABLE IF NOT EXISTS snapshots (
        date TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL,
        url TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(date, source)
    );
    CREATE TABLE IF NOT EXISTS downloads (
        source TEXT NOT NULL, period TEXT NOT NULL, url TEXT NOT NULL,
        csv_text TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(source, period)
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')
    return db


def save(db, day, source, payload, url):
    import json
    db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?) ON CONFLICT(date,source) DO UPDATE SET payload=excluded.payload,url=excluded.url,fetched_at=excluded.fetched_at",
               (str(day), source, json.dumps(payload, ensure_ascii=False), url, datetime.now(ZoneInfo("Asia/Taipei")).isoformat()))


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LocalStockReport/0.1)", "Accept": "text/csv,*/*"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read(2_000_000)
            return decode_csv(raw)
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise DataError("下載失敗")


def sync(path, start, end=None, refresh=False, progress=print, downloader=fetch, delay=0.4):
    end = end or today()
    if start > end:
        raise ValueError("起始日期不可晚於結束日期")
    if end > today():
        raise ValueError("結束日期不可晚於今天")
    errors, pending, count = [], [], 0
    with connect(path) as db:
        db.execute("INSERT INTO settings VALUES ('start',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (start.isoformat(),))
        month = start.replace(day=1)
        while month <= end:
            url = SOURCES["market"].format(date=month.strftime("%Y%m%d"))
            progress(f"下載 {month:%Y-%m} 市場成交資訊…")
            try:
                text = downloader(url)
                records = parse_market(text, month)
                with db:
                    for record in records:
                        day = date.fromisoformat(record["date"])
                        if start <= day <= end:
                            save(db, day, "market", record, url)
                    archive(db, "market", str(month), text, url)
            except Exception as exc:
                errors.append(f"{month:%Y-%m} 市場：{exc}")
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            time.sleep(delay)
        days = [r[0] for r in db.execute("SELECT date FROM snapshots WHERE source='market' AND date BETWEEN ? AND ? ORDER BY date", (str(start), str(end)))]
        for day_text in days:
            day = date.fromisoformat(day_text)
            for source, parser in (("institutions", parse_institutions), ("margin", parse_margin)):
                exists = db.execute("SELECT 1 FROM snapshots WHERE date=? AND source=?", (day_text, source)).fetchone()
                # 重抓最近三個交易日，接受官方更正；歷史缺漏永遠補抓。
                if exists and not refresh and day_text not in days[-3:]:
                    continue
                progress(f"下載 {day} {'三大法人' if source == 'institutions' else '融資券'}…")
                url = SOURCES[source].format(date=day.strftime("%Y%m%d"))
                try:
                    text = downloader(url)
                    payload = parser(text, day)
                    if payload is None:
                        pending.append(f"{day} {source} 尚未公布")
                    else:
                        with db:
                            save(db, day, source, payload, url)
                            archive(db, source, str(day), text, url)
                        count += 1
                except Exception as exc:
                    errors.append(f"{day} {source}：{exc}")
                time.sleep(delay)
    return {"updated": count, "errors": errors, "pending": pending, "market_dates": len(days)}


def archive(db, source, period, text, url):
    db.execute("INSERT INTO downloads VALUES (?,?,?,?,?) ON CONFLICT(source,period) DO UPDATE SET csv_text=excluded.csv_text,url=excluded.url,fetched_at=excluded.fetched_at",
               (source, period, url, text, datetime.now(ZoneInfo("Asia/Taipei")).isoformat()))


def history(path=DEFAULT_DB):
    import json
    with connect(path) as db:
        setting = db.execute("SELECT value FROM settings WHERE key='start'").fetchone()
        start = setting[0] if setting else "0001-01-01"
        result = {}
        for row in db.execute("SELECT * FROM snapshots WHERE date>=? ORDER BY date", (start,)):
            entry = result.setdefault(row["date"], {"date": row["date"], "sources": {}})
            entry.update(json.loads(row["payload"]))
            entry["sources"][row["source"]] = {"url": row["url"], "fetched_at": row["fetched_at"]}
        return list(result.values())


def configured_start(path):
    with connect(path) as db:
        row = db.execute("SELECT value FROM settings WHERE key='start'").fetchone()
    return date.fromisoformat(row[0]) if row else default_start()
