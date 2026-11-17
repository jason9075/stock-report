import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_report.data import DataError, SOURCES, connect, decode_csv, history, parse_institutions, parse_margin, parse_market, parse_ohlc, parse_put_call, sync
from stock_report.report import delta, export, markdown, pct

FIXTURES = Path(__file__).parent / 'fixtures'
DAY = date(2026, 11, 11)


def fixture(source):
    return (FIXTURES / f'{source}.csv').read_text(encoding='utf-8')


class ParsingTests(unittest.TestCase):
    def test_institutions_reconcile_without_double_counting(self):
        result = parse_institutions(fixture('institutions'), DAY)
        self.assertEqual(result['foreign_net'], -766_443_336)
        self.assertEqual(result['trust_net'], 18_585_463_465)
        self.assertEqual(result['dealer_net'], 6_256_872_866)
        self.assertEqual(result['total_net'], 24_075_892_995)
        self.assertEqual(result['foreign_net'] + result['trust_net'] + result['dealer_net'], result['total_net'])

    def test_wrong_date_and_incorrect_totals_rejected(self):
        with self.assertRaises(DataError):
            parse_institutions(fixture('institutions'), date(2026, 11, 10))
        with self.assertRaises(DataError):
            parse_institutions(fixture('institutions').replace('24,075,892,995', '24,075,892,994'), DAY)

    def test_margin_units_and_official_adjusted_previous(self):
        result = parse_margin(fixture('margin'), DAY)
        self.assertEqual(result['financing_balance'], 541_158_093_000)
        self.assertEqual(delta(result, 'financing'), 4_479_361_000)
        self.assertEqual(delta(result, 'short'), -2112)
        self.assertAlmostEqual(pct(result, 'financing'), .834644771, places=6)
        # 原文的融券增加 1.1 萬與此份官方報表不符，不能硬寫成貼文數字。
        self.assertNotEqual(delta(result, 'short'), 11_000)

    def test_market_roc_dates_and_previous_close(self):
        rows = parse_market(fixture('market'), DAY.replace(day=1))
        self.assertEqual(rows[0]['date'], '2026-11-02')
        self.assertEqual(rows[-1]['turnover'], 876_295_459_349)
        self.assertAlmostEqual(rows[-1]['index_pct'], 1545.23 / 42711.92 * 100)
        with self.assertRaises(DataError):
            parse_market(fixture('market'), date(2026, 10, 1))

    def test_index_ohlc_parsed_and_validated(self):
        rows = parse_ohlc(fixture('ohlc'), DAY.replace(day=1))
        self.assertEqual(rows[-1], {'date': '2026-11-11', 'open': 43135.76, 'high': 44257.15, 'low': 42708.05})
        with self.assertRaises(DataError):
            parse_ohlc(fixture('ohlc'), date(2026, 10, 1))
        with self.assertRaises(DataError):
            parse_ohlc(fixture('ohlc').replace('"44,257.15","42,708.05"', '"42,000.00","42,708.05"'), DAY.replace(day=1))

    def test_put_call_official_percentages_and_validation(self):
        record = parse_put_call(fixture('put_call'), DAY.replace(day=1))[0]
        self.assertEqual(record['date'], DAY.isoformat())
        self.assertEqual(record['put_call_oi_pct'], 65.17)
        self.assertEqual(record['put_call_volume_pct'], 107.08)
        self.assertEqual(record['put_oi'], 57877)
        for text in (fixture('put_call').replace('65.17', '165.17'),
                     fixture('put_call').replace('88811', '0'),
                     fixture('put_call').replace('107.08', 'NaN'),
                     fixture('put_call').replace('買權成交量,', '未知欄位,'),
                     '<html>Denied</html>'):
            with self.assertRaises(DataError):
                parse_put_call(text, DAY.replace(day=1))
        with self.assertRaises(DataError):
            parse_put_call(fixture('put_call'), date(2026, 10, 1))
        self.assertEqual(parse_put_call(fixture('put_call').splitlines()[0], DAY), [])

    def test_blank_is_pending_html_is_error_and_encodings_supported(self):
        self.assertIsNone(parse_margin('\r\n', DAY))
        self.assertEqual(parse_market('', DAY), [])
        with self.assertRaises(DataError):
            parse_margin('<html>Denied</html>', DAY)
        for encoding in ('cp950', 'utf-8-sig'):
            self.assertIn('信用交易', decode_csv(fixture('margin').encode(encoding)))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / 'local.sqlite3'
        # 將官方月報裁成一日，測試不依賴外部網路。
        lines = fixture('market').splitlines()
        self.market = '\n'.join(lines[:2] + [line for line in lines if line.startswith('"115/11/11"')])
        self.ohlc = '\n'.join(line for line in fixture('ohlc').splitlines() if not line.startswith('"115/11/10"'))
        self.requests = []

    def download(self, url):
        self.requests.append(url)
        if 'FMTQIK' in url:
            return self.market
        if 'MI_5MINS_HIST' in url:
            return self.ohlc
        if 'dlPcRatioDown' in url:
            return fixture('put_call')
        return fixture('margin' if 'MI_MARGN' in url else 'institutions')

    def run_sync(self, downloader=None):
        return sync(self.db, date(2026, 11, 1), DAY, downloader=downloader or self.download, delay=0, progress=lambda _: None)

    def test_sqlite_idempotent_and_holiday_not_requested(self):
        self.run_sync(); self.run_sync()
        rows = history(self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]['sources']), 5)
        self.assertEqual(rows[0]['open'], 43135.76)
        with connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 5)
            self.assertEqual(db.execute('SELECT count(*) FROM downloads').fetchone()[0], 5)
        self.assertFalse(any('dayDate=20261101' in url for url in self.requests))

    def test_partial_failure_keeps_good_data_and_repairs_missing(self):
        def failure(url):
            if 'MI_MARGN' in url:
                raise OSError('離線')
            return self.download(url)
        result = self.run_sync(failure)
        self.assertEqual(len(result['errors']), 1)
        row = history(self.db)[-1]
        self.assertIn('foreign_net', row)
        self.assertNotIn('financing_balance', row)
        self.assertIn('尚未公布', markdown([row]))
        self.run_sync()
        before = history(self.db)[-1]['financing_balance']
        self.run_sync(failure)
        self.assertEqual(history(self.db)[-1]['financing_balance'], before)

    def test_wrong_date_never_overwrites_database(self):
        self.run_sync()
        result = self.run_sync(lambda url: self.market if 'FMTQIK' in url else self.ohlc if 'MI_5MINS_HIST' in url else fixture('put_call') if 'dlPcRatioDown' in url else fixture('margin' if 'MI_MARGN' in url else 'institutions').replace('11月11日', '11月10日'))
        self.assertEqual(len(result['errors']), 2)
        self.assertEqual(history(self.db)[-1]['foreign_net'], -766_443_336)

    def test_put_call_failure_pending_and_recovery(self):
        def failure(url):
            if 'dlPcRatioDown' in url:
                raise OSError('期交所暫時無法連線')
            return self.download(url)

        result = self.run_sync(failure)
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue(any('Put/Call' in item for item in result['pending']))
        self.assertNotIn('put_call_oi_pct', history(self.db)[-1])
        self.assertIn('尚未公布', markdown(history(self.db)))
        self.run_sync()
        self.run_sync(failure)
        self.assertEqual(history(self.db)[-1]['put_call_oi_pct'], 65.17)

        def corrupt(url):
            text = self.download(url)
            return text.replace('65.17', '165.17') if 'dlPcRatioDown' in url else text

        result = self.run_sync(corrupt)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(history(self.db)[-1]['put_call_oi_pct'], 65.17)

    def test_old_month_put_call_missing_is_retried(self):
        from unittest.mock import patch

        self.run_sync()
        with connect(self.db) as db:
            db.execute("DELETE FROM snapshots WHERE source='put_call'")
        self.requests.clear()

        def download_month(url):
            if '20261101' in url or '2026%2F11%2F01' in url or 'dayDate=' in url or 'MI_MARGN' in url:
                return self.download(url)
            self.requests.append(url)
            return fixture('put_call').splitlines()[0] if 'dlPcRatioDown' in url else ''

        with patch('stock_report.data.today', return_value=date(2027, 3, 1)):
            result = sync(self.db, date(2026, 11, 1), date(2027, 2, 1),
                          downloader=download_month, delay=0, progress=lambda _: None)
        self.assertEqual(result['errors'], [])
        self.assertTrue(any('queryStartDate=2026%2F11%2F01' in url for url in self.requests))
        self.assertEqual(history(self.db)[-1]['put_call_oi_pct'], 65.17)

    def test_export_is_local_and_date_filter_works(self):
        self.run_sync()
        dest = export(self.db, Path(self.directory.name) / 'report.html')
        text = dest.read_text()
        self.assertIn('65.17%', text)
        self.assertIn('107.08%', text)
        self.assertIn('57,877', text)
        self.assertIn('<table', text)
        self.assertIn('2026-11-11', text)
        self.assertIn('-766,443,336 元', text)
        self.assertIn('541,158,093,000 元', text)
        self.assertIn('+4,479,361,000 元', text)
        self.assertIn('#2e3440', text)
        self.assertNotIn('<script', text)
        self.assertIn('尚無資料', markdown([]))
        dest = export(self.db, Path(self.directory.name) / 'empty.md', '2026-11-01')
        self.assertIn('尚無資料', dest.read_text())

    def test_sparkline_hover_updates_tooltip_and_renders(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from stock_report.gui import TrendChart, tray_lines
        app = QApplication.instance() or QApplication([])
        self.run_sync()
        rows = history(self.db)
        lines = tray_lines(rows[-1])
        self.assertEqual(len(lines), 7)
        self.assertIn('台指：44,257.15（+1,545.23 / +3.62%）', lines[1])
        self.assertIn('外資：-7.66 億', lines[2])
        self.assertIn('投信：+185.85 億', lines[3])
        self.assertIn('自營商：+62.57 億', lines[4])
        self.assertIn('融資：+44.79 億', lines[5])
        self.assertIn('融券：-2,112 單位', lines[6])
        chart = TrendChart('外資買賣超 · 億元', 'bar', 'foreign_net', 100_000_000)
        chart.resize(420, 240)
        chart.update_data(rows)
        self.assertEqual(chart.fmt(-766_443_336), '-7.66 億')
        self.assertEqual(chart.fmt_exact(-766_443_336), '-766,443,336 元')
        chart.set_hover(0)
        self.assertEqual(chart.toolTip(), '')
        self.assertFalse(chart.grab().isNull())
        chart.set_hover(None)
        self.assertIsNone(chart.hover_index)
        kline = TrendChart('加權指數 K 線', 'candle')
        kline.resize(800, 260)
        kline.update_data(rows, 'day', log=True)
        self.assertEqual(kline.series[-1]['o'], 43135.76)
        base_lo, base_hi = kline.value_range()
        kline.y_scale = 2.0
        scaled_lo, scaled_hi = kline.value_range()
        self.assertLess(scaled_lo, base_lo)
        self.assertGreater(scaled_hi, base_hi)
        kline.set_hover(0, 100)
        self.assertEqual(kline.hover_y, 100)
        five_days = [dict(rows[0], date=f'2026-11-0{i}') for i in range(1, 6)]
        kline.update_data(five_days, 'day', log=True, show_ma=True)
        self.assertTrue(any(r[0] == 'MA5' for r in kline.card_rows(kline.series[-1], len(kline.series) - 1)))
        kline.update_data(five_days, 'day', log=True, show_ma=False)
        self.assertFalse(kline.show_ma)
        self.assertFalse(any(r[0].startswith('MA') for r in kline.card_rows(kline.series[-1], len(kline.series) - 1)))
        self.assertFalse(kline.grab().isNull())

    def test_chart_series_aggregation_and_indicators(self):
        from stock_report.gui import adaptive_log_ticks, build_series, moving_average, nice_ticks
        rows = [
            {'date': '2026-10-30', 'foreign_net': 100, 'open': 10, 'high': 12, 'low': 9, 'close': 11, 'turnover': 5},
            {'date': '2026-11-02', 'foreign_net': 200, 'open': 11, 'high': 15, 'low': 10, 'close': 14, 'turnover': 6},
            {'date': '2026-11-03', 'foreign_net': -50, 'open': 14, 'high': 14, 'low': 8, 'close': 9, 'turnover': 7},
        ]
        week = build_series(rows, 'week', 'bar', 'foreign_net')
        self.assertEqual([(p['label'], p['value']) for p in week], [('2026-10-30', 100), ('2026-11-02~11-03', 150)])
        month = build_series(rows, 'month', 'candle')
        self.assertEqual({k: month[1][k] for k in ('label', 'o', 'h', 'l', 'c', 'v')}, {'label': '2026-11', 'o': 11, 'h': 15, 'l': 8, 'c': 9, 'v': 13})
        self.assertEqual(moving_average([1, 2, 3, None, 5], 2), [None, 1.5, 2.5, None, None])
        self.assertEqual(nice_ticks(-3.2, 7.9, 5), [-2.5, 0.0, 2.5, 5.0, 7.5])
        log_ticks = adaptive_log_ticks(12_000, 48_000, 170)
        self.assertTrue(all(12_000 <= t <= 48_000 for t in log_ticks))
        self.assertGreater(log_ticks[-1] - log_ticks[-2], log_ticks[1] - log_ticks[0])

if __name__ == '__main__':
    unittest.main()
