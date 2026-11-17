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
    "ohlc": "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?response=csv&date={date}",
    "put_call": "https://www.taifex.com.tw/cht/3/dlPcRatioDown?queryStartDate={start}&queryEndDate={end}",
}


def today():
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def default_start():
    # 預設收集當年 1/1 起的所有交易日資料。
    return date(today().year, 1, 1)


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


def parse_ohlc(text, month):
    """加權指數月報：開高低收；收盤沿用市場成交資訊，這裡只存開高低。"""
    rows = rows_of(text)
    result = []
    for row in rows:
        if not row or not re.fullmatch(r"\d{2,4}/\d{2}/\d{2}", row[0]):
            continue
        if len(row) < 5:
            raise DataError("指數報表欄位不完整")
        y, m, d = map(int, row[0].split("/"))
        day = date(y + 1911 if y < 1911 else y, m, d)
        if (day.year, day.month) != (month.year, month.month):
            raise DataError("指數報表月份不符")
        o, h, l, c = map(number, row[1:5])
        if not (l <= min(o, c) and max(o, c) <= h):
            raise DataError(f"{day} 指數開高低收不合理")
        result.append({"date": day.isoformat(), "open": float(o), "high": float(h), "low": float(l)})
    if text.strip() and not result:
        raise DataError("指數報表無可辨識的交易資料")
    return result


def parse_put_call(text, month):
    """期交所 TXO 買賣權比率；保留官方百分比與原始口數。"""
    rows = rows_of(text)
    header = ['日期', '賣權成交量', '買權成交量', '買賣權成交量比率%',
              '賣權未平倉量', '買權未平倉量', '買賣權未平倉量比率%']
    if not rows or rows[0][:7] != header:
        raise DataError('Put/Call 報表欄位不完整')
    result, seen = [], set()
    for row in rows[1:]:
        if len(row) < 7:
            raise DataError('Put/Call 報表欄位不完整')
        try:
            day = datetime.strptime(row[0], '%Y/%m/%d').date()
        except ValueError as exc:
            raise DataError('Put/Call 報表日期無法辨識') from exc
        if (day.year, day.month) != (month.year, month.month) or day in seen:
            raise DataError('Put/Call 報表月份不符或日期重複')
        seen.add(day)
        record = {'date': day.isoformat()}
        for offset, kind in ((1, 'volume'), (4, 'oi')):
            put, call = map(integer, row[offset:offset + 2])
            ratio = number(row[offset + 2])
            if put < 0 or call <= 0 or not ratio.is_finite() or ratio < 0:
                raise DataError('Put/Call 口數或比率不合理')
            if abs(ratio - Decimal(put) / Decimal(call) * 100) > Decimal('0.01'):
                raise DataError('Put/Call 比率與口數無法對帳')
            record.update({f'put_{kind}': put, f'call_{kind}': call,
                           f'put_call_{kind}_pct': float(ratio)})
        result.append(record)
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
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read(2_000_000)
            return decode_csv(raw)
        except (OSError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    raise DataError("下載失敗")


def sync(path, start, end=None, refresh=False, progress=print, downloader=fetch, delay=1.2):
    end = end or today()
    if start > end:
        raise ValueError("起始日期不可晚於結束日期")
    if end > today():
        raise ValueError("結束日期不可晚於今天")
    errors, pending, count = [], [], 0
    with connect(path) as db:
        db.execute("INSERT INTO settings VALUES ('start',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (start.isoformat(),))
        month = start.replace(day=1)
        recent_month = (end.replace(day=1) - timedelta(days=1)).replace(day=1)
        while month <= end:
            for source, parser, title in (("market", parse_market, "市場成交資訊"), ("ohlc", parse_ohlc, "加權指數開高低"), ("put_call", parse_put_call, "臺指選擇權 Put/Call")):
                has_month = db.execute("SELECT 1 FROM downloads WHERE source=? AND period=?", (source, str(month))).fetchone()
                missing_put_call = source == 'put_call' and db.execute(
                    "SELECT 1 FROM snapshots m WHERE m.source='market' AND m.date BETWEEN ? AND ? "
                    "AND NOT EXISTS (SELECT 1 FROM snapshots p WHERE p.date=m.date AND p.source='put_call') LIMIT 1",
                    (str(max(start, month)), str(min(end, (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)))),
                ).fetchone()
                if has_month and not refresh and month < recent_month and not missing_put_call:
                    continue
                month_end = min((month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), end)
                url = SOURCES[source].format(date=month.strftime("%Y%m%d"), start=month.strftime('%Y%%2F%m%%2F%d'), end=month_end.strftime('%Y%%2F%m%%2F%d'))
                progress(f"下載 {month:%Y-%m} {title}…")
                try:
                    text = downloader(url)
                    records = parser(text, month)
                    with db:
                        for record in records:
                            day = date.fromisoformat(record["date"])
                            if start <= day <= end:
                                save(db, day, source, record, url)
                        archive(db, source, str(month), text, url)
                except Exception as exc:
                    errors.append(f"{month:%Y-%m} {title}：{exc}")
                time.sleep(delay)
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        days = [r[0] for r in db.execute("SELECT date FROM snapshots WHERE source='market' AND date BETWEEN ? AND ? ORDER BY date", (str(start), str(end)))]
        for day_text in days:
            if not db.execute("SELECT 1 FROM snapshots WHERE date=? AND source='put_call'", (day_text,)).fetchone():
                pending.append(f'{day_text} Put/Call 尚未公布／下載')
        for idx, day_text in enumerate(reversed(days), 1):
            day = date.fromisoformat(day_text)
            for source, parser in (("institutions", parse_institutions), ("margin", parse_margin)):
                exists = db.execute("SELECT 1 FROM snapshots WHERE date=? AND source=?", (day_text, source)).fetchone()
                # 重抓最近三個交易日，接受官方更正；歷史缺漏永遠補抓。
                if exists and not refresh and day_text not in days[-3:]:
                    continue
                progress(f"下載 {day} {'三大法人' if source == 'institutions' else '融資券'}…（{idx}/{len(days)} 日）")
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
