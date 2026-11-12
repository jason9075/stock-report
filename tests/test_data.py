import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_report.data import DataError, SOURCES, connect, decode_csv, history, parse_institutions, parse_margin, parse_market, sync
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
        self.requests = []

    def download(self, url):
        self.requests.append(url)
        if 'FMTQIK' in url:
            return self.market
        return fixture('margin' if 'MI_MARGN' in url else 'institutions')

    def run_sync(self, downloader=None):
        return sync(self.db, date(2026, 11, 1), DAY, downloader=downloader or self.download, delay=0, progress=lambda _: None)

    def test_sqlite_idempotent_and_holiday_not_requested(self):
        self.run_sync(); self.run_sync()
        rows = history(self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]['sources']), 3)
        with connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT count(*) FROM downloads').fetchone()[0], 3)
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
        result = self.run_sync(lambda url: self.market if 'FMTQIK' in url else fixture('margin' if 'MI_MARGN' in url else 'institutions').replace('11月11日', '11月10日'))
        self.assertEqual(len(result['errors']), 2)
        self.assertEqual(history(self.db)[-1]['foreign_net'], -766_443_336)

    def test_export_is_local_and_date_filter_works(self):
        self.run_sync()
        dest = export(self.db, Path(self.directory.name) / 'report.html')
        text = dest.read_text()
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


if __name__ == '__main__':
    unittest.main()
