from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .data import DEFAULT_DB, ROOT, configured_start, history, sync, today
from .report import export, markdown


def main(argv=None):
    parser = argparse.ArgumentParser(description="台股數字核對：證交所公開 CSV → SQLite → 報告／桌面小工具")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 路徑")
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser("sync", help="下載並補齊交易日資料")
    update.add_argument("--start", type=date.fromisoformat, help="起始日期 YYYY-MM-DD（預設最近一次 11/1，之後沿用）")
    update.add_argument("--end", type=date.fromisoformat, help="結束日期，預設台北今日")
    update.add_argument("--refresh", action="store_true", help="重抓全部期間，包括已有資料")
    report = commands.add_parser("report", help="查看或匯出報告")
    report.add_argument("--output", type=Path, help="輸出 .html 或 .md")
    report.add_argument("--date", type=date.fromisoformat, help="查看該日期以前最近一個交易日")
    report.add_argument("--json", action="store_true", help="輸出所有日期的原始數值（新臺幣元）")
    gui = commands.add_parser("widget", help="開啟桌面與系統匣小工具")
    gui.add_argument("--compact", action="store_true", help="直接開啟小視窗")
    gui.add_argument("--tray", action="store_true", help="啟動時只顯示系統匣圖示")
    gui.add_argument("--screenshot", type=Path, help=argparse.SUPPRESS)
    commands.add_parser("desktop-install", help="安裝 Linux 應用程式啟動捷徑（不加入開機自啟）")
    args = parser.parse_args(argv)
    try:
        if args.command == "sync":
            result = sync(args.db, args.start or configured_start(args.db), args.end, args.refresh)
            print(f"完成：{result['market_dates']} 個交易日，更新 {result['updated']} 份法人／融資券報表。")
            for item in result['pending'] + result['errors']:
                print(item, file=sys.stderr)
            rows = history(args.db)
            print(f"最新本機資料日：{rows[-1]['date'] if rows else '尚無資料'}；台北今日：{today()}")
            return 1 if result['errors'] else 0
        if args.command == "report":
            asof = str(args.date) if args.date else None
            rows = history(args.db)
            if asof:
                rows = [r for r in rows if r['date'] <= asof]
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            elif args.output:
                print(export(args.db, args.output, asof))
            else:
                print(markdown(rows))
            return 0
        if args.command == "widget":
            try:
                from .gui import run
            except ImportError as exc:
                print(f"桌面元件尚未安裝：{exc}。請執行 uv sync --extra gui", file=sys.stderr)
                return 1
            return run(args.db, args.compact, args.screenshot, start_in_tray=args.tray)
        if args.command == "desktop-install":
            if not sys.platform.startswith('linux'):
                parser.error("此啟動捷徑安裝指令適用 Linux；其他平台請執行 widget")
            applications = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'applications'
            applications.mkdir(parents=True, exist_ok=True)
            # .desktop 使用雙引號規則，不使用 shell 展開。
            def quote(value):
                return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
            destination = applications / 'tw-stock-report.desktop'
            command = f'{quote(sys.executable)} -m stock_report --db {quote(args.db.resolve())} widget --compact'
            destination.write_text(f'[Desktop Entry]\nType=Application\nName=台股數字核對\nComment=上市三大法人與融資券盤後數據\nExec={command}\nPath={ROOT}\nIcon=office-chart-line\nTerminal=false\nCategories=Office;Finance;\nStartupNotify=true\n', encoding='utf-8')
            print(f"已建立應用程式捷徑：{destination}")
            return 0
    except (ValueError, OSError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    return 0
