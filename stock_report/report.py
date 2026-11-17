from __future__ import annotations

from pathlib import Path

from .data import history, today

YI = 100_000_000


def money(value, signed=True):
    return "尚未公布" if value is None else f"{value / YI:+,.2f}" if signed else f"{value / YI:,.2f}"


def exact(value, signed=True):
    """Format a stored value without scaling or rounding its integer digits."""
    return "尚未公布" if value is None else f"{value:+,}" if signed else f"{value:,}"


def delta(row, key):
    a, b = row.get(f"{key}_balance"), row.get(f"{key}_previous")
    return None if a is None or b is None else a - b


def pct(row, key):
    change, previous = delta(row, key), row.get(f"{key}_previous")
    return None if change is None or not previous else change / previous * 100


def signed(value, digits=0):
    return "尚未公布" if value is None else f"{value:+,.{digits}f}"


def ratio(value):
    return "尚未公布" if value is None else f"{value:,.2f}%"


def metrics(row):
    return [
        ("外資及陸資", money(row.get("foreign_net")), "億元", "institutions"),
        ("投信", money(row.get("trust_net")), "億元", "institutions"),
        ("自營商", money(row.get("dealer_net")), "億元", "institutions"),
        ("三大法人合計", money(row.get("total_net")), "億元", "institutions"),
        ("融資金額增減", money(delta(row, "financing")), "億元", "margin"),
        ("融券餘額增減", signed(delta(row, "short")), "交易單位", "margin"),
    ]


def observations(rows, row):
    notes = []
    previous = next((r for r in reversed(rows) if r["date"] < row["date"] and "market" in r["sources"]), None)
    if "total_net" in row:
        net = row["total_net"]
        notes.append(f"三大法人當日{'買超' if net >= 0 else '賣超'} {abs(net) / YI:,.2f} 億元。")
        if previous and "total_net" in previous and previous["total_net"] < 0 < net:
            notes.append("相較前一交易日，三大法人合計由賣超轉為買超。")
    if previous and row.get("foreign_net", 0) < 0 and previous.get("foreign_net", 0) < 0:
        difference = abs(row["foreign_net"]) - abs(previous["foreign_net"])
        notes.append(f"外資賣超金額較前一交易日{'擴大' if difference > 0 else '縮小' if difference < 0 else '持平'}{f' {abs(difference) / YI:,.2f} 億元' if difference else ''}。")
    if "financing_balance" in row:
        notes.append(f"融資餘額 {money(row['financing_balance'], False)} 億元，增減 {money(delta(row, 'financing'))} 億元（{signed(pct(row, 'financing'), 2)}%）。")
    if "short_balance" in row:
        notes.append(f"融券餘額 {row['short_balance']:,} 交易單位，增減 {signed(delta(row, 'short'))}。融券不包含借券賣出，不能代表全部放空部位。")
    if previous and row.get("turnover") is not None and previous.get("turnover"):
        change = (row["turnover"] / previous["turnover"] - 1) * 100
        notes.append(f"成交金額 {money(row['turnover'], False)} 億元，較前一交易日 {change:+.2f}%。量縮或量增本身無法確認買賣力道的成因。")
    if row.get("index_pct", 0) > 0 and (growth := pct(row, "financing")) is not None:
        notes.append(f"大盤漲幅 {row['index_pct']:.2f}%，融資金額增幅 {growth:.2f}%；兩者基礎不同，僅供對照，不能據此斷言無人追價。")
    return notes


def markdown(rows, row=None):
    if not rows:
        return "# 台股數字核對\n\n尚無資料，請先更新。\n"
    row = row or rows[-1]
    lines = [f"# 台股數字核對｜{row['date']}", "", "範圍：上市集中市場＋臺指選擇權（TXO）；盤後官方數據。正數為買超／增加，負數為賣超／減少。", ""]
    if row["date"] != today().isoformat():
        lines += [f"資料日為 {row['date']}，不是今天 {today()}。休市或盤後資料尚未公布時會保留最近資料。", ""]
    if missing := [label for source, label in (("market", "大盤"), ("institutions", "法人"), ("margin", "融資券"), ("put_call", "Put/Call")) if source not in row["sources"]]:
        lines += [f"此日尚缺：{'、'.join(missing)}。空缺不以零代替。", ""]
    lines += ["| 指標 | 閱讀數值 | 完整數值 |", "| --- | ---: | ---: |"]
    raw_metrics = [row.get(k) for k in ('foreign_net', 'trust_net', 'dealer_net', 'total_net')] + [delta(row, 'financing'), delta(row, 'short')]
    for (name, value, unit, _), raw in zip(metrics(row), raw_metrics):
        raw_unit = '交易單位' if unit == '交易單位' else '元'
        lines.append(f"| {name} | {value} {unit} | {exact(raw)} {raw_unit} |")
    lines += [f"| 融資餘額 | {money(row.get('financing_balance'), False)} 億元 | {exact(row.get('financing_balance'), False)} 元 |",
              f"| 融券餘額 | {exact(row.get('short_balance'), False)} 交易單位 | {exact(row.get('short_balance'), False)} 交易單位 |"]
    lines += ["", "## 臺指選擇權 Put/Call Ratio", "",
              "比率＝賣權（Put）÷買權（Call）×100%；100% 等於 1 倍。週到期與各到期月份契約合併計算。", "",
              "| 項目 | 賣權（口） | 買權（口） | P/C 比率 |", "| --- | ---: | ---: | ---: |"]
    for title, kind in (("未平倉量", "oi"), ("成交量", "volume")):
        lines.append(f"| {title} | {exact(row.get('put_' + kind), False)} | {exact(row.get('call_' + kind), False)} | {ratio(row.get('put_call_' + kind + '_pct'))} |")
    lines += ["", "## 買進與賣出", "", "| 法人 | 買進（億元） | 賣出（億元） | 買賣超（億元） |", "| --- | ---: | ---: | ---: |"]
    for name, key in (("外資及陸資", "foreign"), ("投信", "trust"), ("自營商自行買賣", "dealer_self"), ("自營商避險", "dealer_hedge"), ("合計", "total")):
        lines.append(f"| {name} | {money(row.get(key+'_buy'), False)} | {money(row.get(key+'_sell'), False)} | {money(row.get(key+'_net'))} |")
    lines += ["", "## 融資券明細", "", "| 項目 | 買進 | 賣出 | 現金／券償還 | 前日餘額 | 今日餘額 | 增減 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, key, monetary in (("融資金額（億元）", "financing", True), ("融資交易單位", "financing_lots", False), ("融券交易單位", "short", False)):
        values = [row.get(f"{key}_{field}") for field in ("buy", "sell", "repay", "previous", "balance")]
        cells = [money(v, False) if monetary else '尚未公布' if v is None else f'{v:,}' for v in values]
        cells.append(money(delta(row, key)) if monetary else signed(delta(row, key)))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## 數字對照", ""] + [f"- {note}" for note in observations(rows, row)]
    lines += ["", "## 近期交易日", "", "| 日期 | 外資（億） | 投信（億） | 自營商（億） | 合計（億） | 融資增減（億） | 融券增減（交易單位） | 大盤漲跌 | 成交額（億） | P/C 未平倉量 | P/C 成交量 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in [r for r in rows if r["date"] <= row["date"]][-10:]:
        market_pct = f"{r['index_pct']:+.2f}%" if "index_pct" in r else "尚未公布"
        lines.append(f"| {r['date']} | {money(r.get('foreign_net'))} | {money(r.get('trust_net'))} | {money(r.get('dealer_net'))} | {money(r.get('total_net'))} | {money(delta(r, 'financing'))} | {signed(delta(r, 'short'))} | {market_pct} | {money(r.get('turnover'), False)} | {ratio(r.get('put_call_oi_pct'))} | {ratio(r.get('put_call_volume_pct'))} |")
    lines += ["", "## 口徑與來源", "", "- 金額統一以新臺幣元入庫，畫面換算億元；融資金額原始 CSV 單位為仟元。", "- 融券沿用官方「交易單位」，一般股票為張；不把不同商品一律換成股數。", "- 每日融資券增減＝同日報表的今日餘額－前日餘額。前日餘額可能經官方調帳，並非直接減去資料庫上一天的今日餘額。", "- 外資欄為外資及陸資（不含外資自營商）；自營商含自行買賣與避險。外資自營商已計入自營商，不能再加一次。", "- 今日餘額可能修正；每次更新會重抓最近三個交易日。可使用 --refresh 重抓完整期間。", "- Put/Call 為臺指選擇權統計，不代表法人淨多空或直接買賣訊號；未納入上櫃、期貨與借券。這些資料不足以推算融資戶損益、維持率或斷定未來方向。", ""]
    for source, meta in row["sources"].items():
        label = {"market": "市場成交資訊", "ohlc": "加權指數歷史資料（開高低）", "institutions": "三大法人買賣金額", "margin": "信用交易統計", "put_call": "臺指選擇權 Put/Call 比（期交所）"}.get(source, source)
        lines.append(f"- [{label}]({meta['url']})；擷取時間 {meta['fetched_at']}")
    return "\n".join(lines) + "\n"


def export(path, destination, asof=None):
    rows = history(path)
    if asof:
        rows = [r for r in rows if r["date"] <= asof]
    content = markdown(rows)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".html":
        # 完全本機、無 CDN；表格在窄螢幕也能橫向捲動。
        from .render import markdown_html
        from .theme import REPORT_CSS
        content = '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>台股數字核對</title><style>' + REPORT_CSS + '</style>' + markdown_html(content) + '</html>'
    destination.write_text(content, encoding="utf-8")
    return destination
