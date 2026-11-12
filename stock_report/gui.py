from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QPointF, QRectF, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton,
    QSystemTrayIcon, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .data import DEFAULT_DB, configured_start, history, sync, today
from .render import markdown_html
from .report import delta, exact, export, markdown, money, pct, signed
from .theme import GREEN, MUTED, RED, YELLOW

STYLE = """
QWidget {background:#2e3440;color:#e5e9f0;font-family:'Noto Sans CJK TC','Microsoft JhengHei',sans-serif;font-size:13px;}
QLabel {background:transparent;}
QLabel#title {font-size:21px;font-weight:700;color:#eceff4;}
QLabel#muted {color:#b0bbcc;font-size:12px;}
QLabel#detail {color:#98a4b7;font-size:10px;}
QLabel#section {color:#d8dee9;font-size:13px;font-weight:600;}
QLabel#hero {font-family:'DejaVu Sans Mono',monospace;font-size:30px;font-weight:600;color:#eceff4;}
QLabel#number {font-family:'DejaVu Sans Mono',monospace;font-size:20px;color:#eceff4;}
QLabel#smallNumber {font-family:'DejaVu Sans Mono',monospace;font-size:16px;color:#eceff4;}
QLabel#badge {background:#434c5e;color:#88c0d0;border-radius:5px;padding:5px 9px;font-size:11px;}
QFrame#panel {background:#3b4252;border:1px solid #434c5e;border-radius:10px;}
QFrame#panel QWidget {background:transparent;}
QFrame#rule {background:#4c566a;max-height:1px;min-height:1px;border:0;}
QPushButton {background:#3b4252;border:1px solid #4c566a;border-radius:6px;padding:7px 12px;color:#d8dee9;}
QPushButton:hover {background:#434c5e;border-color:#81a1c1;color:#eceff4;}
QPushButton:pressed,QPushButton:checked {background:#4c566a;border-color:#88c0d0;}
QPushButton:disabled {color:#4c566a;border-color:#3b4252;background:#2e3440;}
QPushButton#primary {background:#88c0d0;border-color:#88c0d0;color:#2e3440;font-size:20px;padding:0;}
QPushButton#primary:hover {background:#8fbcbb;}
QPushButton#primary:disabled {background:#434c5e;border-color:#434c5e;}
QPushButton#nav {font-size:24px;padding:0;background:transparent;border:0;}
QPushButton#nav:hover {background:#434c5e;}
QPushButton#pin {background:transparent;border:1px solid #4c566a;font-size:20px;padding:0;}
QPushButton#pin:hover {background:#434c5e;border-color:#81a1c1;}
QPushButton#pin:checked {background:#88c0d0;border:2px solid #8fbcbb;color:#2e3440;}
QPushButton#pin:checked:hover {background:#8fbcbb;}
QComboBox {background:transparent;border:1px solid #4c566a;border-radius:6px;padding:7px 12px;color:#d8dee9;}
QComboBox#date {font-family:'DejaVu Sans Mono',monospace;font-size:18px;font-weight:500;border:0;}
QComboBox:hover {background:#434c5e;}
QComboBox::drop-down {border:0;width:22px;}
QComboBox QAbstractItemView {background:#3b4252;color:#e5e9f0;selection-background-color:#4c566a;}
QTableWidget {background:#2e3440;alternate-background-color:#343b49;border:0;selection-background-color:#434c5e;font-family:'DejaVu Sans Mono',monospace;font-size:12px;}
QHeaderView::section {background:#3b4252;color:#b0bbcc;padding:10px 12px;border:0;font-size:12px;}
QTabWidget::pane {border:0;}
QTabBar::tab {background:transparent;color:#b0bbcc;padding:10px 4px;margin-right:24px;border-bottom:2px solid transparent;}
QTabBar::tab:selected {color:#88c0d0;border-bottom:2px solid #88c0d0;}
QTabBar::tab:hover {color:#eceff4;}
QTextBrowser {border:0;background:#2e3440;padding:8px;color:#d8dee9;selection-background-color:#4c566a;}
QToolTip {background:#434c5e;color:#eceff4;border:1px solid #4c566a;padding:7px;}
QMenu {background:#3b4252;border:1px solid #4c566a;padding:6px;}
QMenu::item {padding:7px 14px;} QMenu::item:selected {background:#434c5e;}
QScrollBar:vertical {background:#2e3440;width:10px;margin:0;}
QScrollBar:horizontal {background:#2e3440;height:10px;margin:0;}
QScrollBar::handle {background:#4c566a;border-radius:4px;min-height:24px;min-width:24px;}
QScrollBar::add-line,QScrollBar::sub-line {width:0;height:0;}
QScrollBar::add-page,QScrollBar::sub-page {background:transparent;}
QWidget[compact="true"] QLabel#title {font-size:17px;}
QWidget[compact="true"] QLabel#hero {font-size:25px;}
QWidget[compact="true"] QLabel#number {font-size:17px;}
QWidget[compact="true"] QLabel#section {font-size:12px;}
QWidget[compact="true"] QLabel#muted {font-size:11px;}
QWidget[compact="true"] QComboBox#date {font-size:15px;}
QWidget[compact="true"] QLabel#badge {font-size:10px;padding:4px 6px;}
"""


def color(value):
    return MUTED if value is None or value == 0 else RED if value > 0 else GREEN


def label(text='', role=None, selectable=False):
    widget = QLabel(text)
    if role:
        widget.setObjectName(role)
    if selectable:
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def rule():
    frame = QFrame(); frame.setObjectName('rule')
    return frame


def amount_html(value, unit='元', signed_value=True):
    return '—' if value is None else f'{exact(value, signed_value)} <span style="font-size:12px;color:{MUTED}">{unit}</span>'


def yi_html(value, signed_value=True):
    return '—' if value is None else f'{money(value, signed_value)} <span style="font-size:12px;color:{MUTED}">億</span>'


def direction(value):
    return '尚未公布' if value is None else '買超' if value > 0 else '賣超' if value < 0 else '買賣持平'


def icon():
    pixmap = QPixmap(64, 64); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor('#3b4252')); painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QColor('#88c0d0'))
    font = QFont(); font.setBold(True); font.setPixelSize(32); painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '台'); painter.end()
    return QIcon(pixmap)


class InstitutionRow(QWidget):
    def __init__(self, name, note):
        super().__init__()
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 4, 0, 4)
        left = QVBoxLayout(); left.setSpacing(3)
        left.addWidget(label(name, 'section'))
        self.note = label(note, 'muted'); left.addWidget(self.note)
        layout.addLayout(left); layout.addStretch()
        right = QVBoxLayout(); right.setSpacing(3)
        self.value = label('—', 'number', True)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self.value)
        layout.addLayout(right)

    def update_value(self, row, key):
        value = row.get(key + '_net')
        self.value.setText(yi_html(value))
        self.value.setStyleSheet(f'color:{color(value)}')
        if value is not None:
            self.setToolTip(f"買賣超 {exact(value)} 元\n買進 {exact(row.get(key + '_buy'), False)} 元\n賣出 {exact(row.get(key + '_sell'), False)} 元")
        else:
            self.setToolTip('尚未公布／下載')
        self.value.setToolTip(self.toolTip())


class CreditMetric(QWidget):
    def __init__(self, name, key, unit):
        super().__init__()
        self.key, self.unit, self.compact = key, unit, False
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 4, 0, 4); layout.setSpacing(4)
        header = QHBoxLayout(); header.addWidget(label(name, 'section')); header.addStretch()
        self.rate = label('', 'muted'); header.addWidget(self.rate); layout.addLayout(header)
        self.balance = label('—', 'number', True); layout.addWidget(self.balance)
        self.change = label('當日增減 —', 'smallNumber', True); layout.addWidget(self.change)
        self.previous = label('前日餘額 —', 'muted', True); self.previous.setWordWrap(True); layout.addWidget(self.previous)
        self.summary = label('', 'detail', True); layout.addWidget(self.summary)
        self.summary.hide()

    def update_value(self, row):
        value, previous = row.get(self.key + '_balance'), row.get(self.key + '_previous')
        change, rate = delta(row, self.key), pct(row, self.key)
        monetary = self.key == 'financing'
        display_unit = '單位' if self.compact and not monetary else self.unit
        self.balance.setText(yi_html(value, False) if monetary else amount_html(value, display_unit, False))
        self.change.setText('當日 ' + (yi_html(change) if monetary else amount_html(change, display_unit)))
        self.balance.setToolTip('尚未公布' if value is None else f'餘額 {exact(value, False)} {self.unit}')
        self.change.setToolTip('尚未公布' if change is None else f'當日增減 {exact(change)} {self.unit}')
        self.previous.setToolTip('尚未公布' if previous is None else f'前日餘額 {exact(previous, False)} {self.unit}')
        self.change.setStyleSheet(f'color:{color(change)};font-size:14px;')
        self.rate.setText('—' if rate is None else f'{rate:+.2f}%')
        self.rate.setStyleSheet(f'color:{color(rate)}')
        self.previous.setText('前日 ' + ('—' if previous is None else f'{money(previous, False)} 億' if monetary else f'{exact(previous, False)} {self.unit}'))
        if self.key == 'financing' and value is not None:
            self.summary.setText(f'{exact(value, False)} 元\n當日 {exact(change)} 元')
        else:
            self.summary.setText('一般股票每交易單位為 1 張')


class Sparkline(QWidget):
    def __init__(self, title, key, scale=1):
        super().__init__()
        self.title, self.key, self.scale, self.points = title, key, scale, []
        self.setMinimumHeight(115)

    def update_data(self, rows):
        self.points = [(r['date'], (delta(r, self.key) if self.key in ('financing', 'short') else r.get(self.key))) for r in rows[-20:]]
        self.setToolTip('\n'.join(f'{d}  {exact(v)}' if v is not None else f'{d}  尚未公布' for d, v in self.points))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(MUTED)); p.drawText(0, 17, self.title)
        values = [v for _, v in self.points if v is not None]
        if not values:
            p.drawText(0, 60, '等待資料'); return
        low, high = min(min(values), 0), max(max(values), 0)
        span = high - low or 1
        left, top, width, height = 56, 36, self.width() - 72, self.height() - 60
        y = lambda v: top + (high - v) / span * height
        p.setPen(QColor('#4c566a'))
        p.drawLine(QPointF(left, y(0)), QPointF(left + width, y(0)))
        p.setPen(QColor(MUTED))
        for v in (high, low):
            p.drawText(QRectF(0, y(v) - 8, 48, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f'{v/self.scale:,.0f}')
        path, active = QPainterPath(), False
        for i, (_, v) in enumerate(self.points):
            if v is None:
                active = False; continue
            point = QPointF(left + i * width / max(len(self.points) - 1, 1), y(v))
            if active:
                path.lineTo(point)
            else:
                path.moveTo(point)
            active = True
        pen = p.pen(); pen.setColor(QColor('#88c0d0')); pen.setWidthF(1.8); p.setPen(pen)
        p.drawPath(path)
        for i, (_, v) in enumerate(self.points):
            if v is not None:
                p.setBrush(QColor('#88c0d0')); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(left + i * width / max(len(self.points)-1, 1), y(v)), 2.5, 2.5)
        p.setPen(QColor(MUTED))
        p.drawText(left, self.height() - 3, self.points[0][0][5:])
        p.drawText(self.width() - 49, self.height() - 3, self.points[-1][0][5:])


class SyncWorker(QThread):
    progress = Signal(str)
    result = Signal(object)

    def __init__(self, path, start):
        super().__init__(); self.path, self.start_date = path, start

    def run(self):
        try:
            self.result.emit(sync(self.path, self.start_date, progress=self.progress.emit))
        except Exception as exc:
            self.result.emit({'updated': 0, 'errors': [str(exc)], 'pending': [], 'market_dates': 0})


class Window(QMainWindow):
    def __init__(self, path, auto_refresh=True):
        super().__init__()
        self.path, self.rows, self.worker = Path(path), [], None
        self.compact, self.quit_after = False, False
        self.setWindowTitle('台股數字核對'); self.setWindowIcon(icon())
        self.resize(1180, 960)
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(24, 20, 24, 16); layout.setSpacing(10)
        top = QHBoxLayout()
        brand = QVBoxLayout(); brand.setSpacing(4)
        brand.addWidget(label('台股數字核對', 'title'))
        self.scope = label('上市集中市場  /  每日盤後', 'muted'); brand.addWidget(self.scope)
        top.addLayout(brand); top.addStretch()
        self.compact_btn = QPushButton('精簡視窗'); self.compact_btn.clicked.connect(self.toggle_compact); top.addWidget(self.compact_btn)
        self.pin_btn = QPushButton('📍'); self.pin_btn.setObjectName('pin')
        self.pin_btn.setFixedSize(38, 36); self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip('尚未置頂 · 點擊開啟')
        self.pin_btn.setAccessibleName('置頂：關閉')
        self.pin_btn.toggled.connect(self.pin); top.addWidget(self.pin_btn)
        layout.addLayout(top)

        controls = QGridLayout(); controls.setContentsMargins(0, 0, 0, 0)
        self.data_badge = label('盤後數據', 'badge')
        controls.addWidget(self.data_badge, 0, 0, Qt.AlignmentFlag.AlignLeft)
        navigation = QWidget(); date_controls = QHBoxLayout(navigation); date_controls.setContentsMargins(0, 0, 0, 0); date_controls.setSpacing(5)
        self.previous_date_btn = self.nav_button('‹', '前一個交易日', 1)
        date_controls.addWidget(self.previous_date_btn)
        self.dates = QComboBox(); self.dates.setObjectName('date'); self.dates.setMinimumWidth(160)
        self.dates.currentIndexChanged.connect(self.render); date_controls.addWidget(self.dates)
        self.next_date_btn = self.nav_button('›', '後一個交易日', -1); date_controls.addWidget(self.next_date_btn)
        controls.addWidget(navigation, 0, 1, Qt.AlignmentFlag.AlignCenter)
        self.refresh_btn = QPushButton('🔄'); self.refresh_btn.setObjectName('primary')
        self.refresh_btn.setFixedSize(38, 36)
        self.refresh_btn.setToolTip('更新資料 · 每 30 分鐘自動更新')
        self.refresh_btn.setAccessibleName('更新資料')
        self.refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_btn, 0, 2, Qt.AlignmentFlag.AlignRight)
        controls.setColumnStretch(0, 1); controls.setColumnStretch(2, 1)
        layout.addLayout(controls)
        self.banner = label('', 'muted'); self.banner.setWordWrap(True); layout.addWidget(self.banner)

        self.market_panel = QFrame(); self.market_panel.setObjectName('panel')
        market = QHBoxLayout(self.market_panel); market.setContentsMargins(18, 12, 18, 12); market.setSpacing(24)
        self.market_values, self.market_notes = [], []
        for title in ('加權指數', '當日漲跌', '市場成交金額'):
            column = QVBoxLayout(); column.setSpacing(5); column.addWidget(label(title, 'muted'))
            value, note = label('—', 'smallNumber', True), label('—', 'muted', True)
            self.market_values.append(value); self.market_notes.append(note)
            column.addWidget(value); column.addWidget(note); market.addLayout(column, 1)
        layout.addWidget(self.market_panel)
        self.compact_market = label('', 'muted', True)
        self.compact_market.hide(); layout.addWidget(self.compact_market)

        self.main_grid = QGridLayout(); self.main_grid.setSpacing(16)
        self.institution_panel = QFrame(); self.institution_panel.setObjectName('panel')
        inst = QVBoxLayout(self.institution_panel); inst.setContentsMargins(22, 18, 22, 16); inst.setSpacing(6)
        heading = QHBoxLayout(); heading.addWidget(label('三大法人', 'section')); heading.addStretch(); heading.addWidget(label('當日買賣超 · 億元', 'muted')); inst.addLayout(heading)
        self.total_value = label('—', 'hero', True); inst.addWidget(self.total_value)
        inst.addWidget(rule())
        self.institution_rows = []
        for title, key, note in (('外資及陸資', 'foreign', '不含外資自營商'), ('投信', 'trust', '證券投資信託'), ('自營商', 'dealer', '自行買賣＋避險')):
            item = InstitutionRow(title, note); inst.addWidget(item); self.institution_rows.append((key, item))
        self.credit_panel = QFrame(); self.credit_panel.setObjectName('panel')
        credit = QVBoxLayout(self.credit_panel); credit.setContentsMargins(22, 18, 22, 16); credit.setSpacing(10)
        heading = QHBoxLayout(); heading.addWidget(label('融資與融券', 'section')); heading.addStretch(); heading.addWidget(label('餘額 / 當日變化', 'muted')); credit.addLayout(heading)
        self.credit_grid = QGridLayout(); self.credit_grid.setHorizontalSpacing(26); self.credit_grid.setVerticalSpacing(14)
        self.financing = CreditMetric('融資餘額', 'financing', '元')
        self.short = CreditMetric('融券餘額', 'short', '交易單位')
        self.short.setToolTip('數量沿用證交所交易單位；一般股票為張。融券餘額不含借券賣出。')
        credit.addLayout(self.credit_grid); credit.addStretch()
        self.credit_note = label('增減採同日報表的前日餘額計算；融券不含借券。', 'muted'); self.credit_note.setWordWrap(True); credit.addWidget(self.credit_note)
        self.arrange_panels(); layout.addLayout(self.main_grid)

        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        overview = QWidget(); ov = QVBoxLayout(overview); ov.setContentsMargins(0, 12, 0, 0); ov.setSpacing(12)
        trends = QWidget(); trends_layout = QVBoxLayout(trends); trends_layout.setContentsMargins(0, 18, 0, 8)
        chart_row = QHBoxLayout(); chart_row.setSpacing(24)
        self.charts = [Sparkline('外資買賣超 · 億元', 'foreign_net', 100_000_000), Sparkline('融資增減 · 億元', 'financing', 100_000_000), Sparkline('融券增減 · 交易單位', 'short')]
        for chart in self.charts:
            chart_row.addWidget(chart)
        trends_layout.addLayout(chart_row, 1)
        trends_layout.addWidget(label('最近 20 個交易日 · 圖上單位依標題標示 · 停留可看逐日完整數值', 'muted'))
        table_tools = QHBoxLayout(); table_tools.addWidget(label('逐日數據', 'section')); table_tools.addWidget(label('點選一列，查看該日明細', 'muted')); table_tools.addStretch()
        self.units = QComboBox(); self.units.addItems(['金額 · 億元', '完整金額 · 元']); self.units.currentIndexChanged.connect(self.render_table); table_tools.addWidget(self.units); ov.addLayout(table_tools)
        self.table = QTableWidget(0, 9); self.table.setMinimumHeight(190)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False); self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(37)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellClicked.connect(self.select_table_date); ov.addWidget(self.table, 1)
        self.tabs.addTab(overview, '歷史數據')
        self.tabs.addTab(trends, '變化趨勢')
        self.browser = QTextBrowser(); self.browser.setOpenExternalLinks(True)
        self.browser.document().setDefaultStyleSheet('body{color:#d8dee9} h1,h2{color:#eceff4} a{color:#88c0d0} th{background:#434c5e} td,th{padding:8px} table{margin:12px 0}')
        self.tabs.addTab(self.browser, '完整報告與來源')
        bottom = QHBoxLayout(); self.status = label('本機紀錄可離線查看', 'muted'); self.status.setWordWrap(True); bottom.addWidget(self.status, 1)
        self.export_btn = QPushButton('匯出報告'); self.export_btn.clicked.connect(self.export_report); bottom.addWidget(self.export_btn); layout.addLayout(bottom)
        self.tray = QSystemTrayIcon(icon(), self); self.tray.setToolTip('台股數字核對')
        menu = QMenu(); self.tray_summary = QAction('尚無數據', menu); self.tray_summary.setEnabled(False); menu.addAction(self.tray_summary)
        menu.addAction('開啟／隱藏', self.toggle_visible); menu.addAction('更新數據', self.refresh)
        menu.addSeparator(); menu.addAction('結束', self.quit_app)
        self.tray.setContextMenu(menu); self.tray.activated.connect(self.tray_clicked)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.load()
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh)
        if auto_refresh:
            self.timer.start(30 * 60 * 1000); QTimer.singleShot(500, self.refresh)

    def nav_button(self, text, title, step):
        button = QPushButton(text); button.setObjectName('nav'); button.setFixedSize(36, 36)
        button.setToolTip(title); button.setAccessibleName(title)
        button.clicked.connect(lambda: self.shift_date(step))
        return button

    def arrange_panels(self):
        self.main_grid.addWidget(self.institution_panel, 0, 0)
        self.main_grid.addWidget(self.credit_panel, 1 if self.compact else 0, 0 if self.compact else 1)
        self.main_grid.setColumnStretch(0, 1)
        self.main_grid.setColumnStretch(1, 0 if self.compact else 1)
        self.credit_grid.addWidget(self.financing, 0, 0)
        self.credit_grid.addWidget(self.short, 0 if self.compact else 1, 1 if self.compact else 0)
        self.credit_grid.setColumnStretch(0, 1)
        self.credit_grid.setColumnStretch(1, 1 if self.compact else 0)

    def toggle_compact(self):
        self.compact = not self.compact
        root = self.centralWidget()
        root.setProperty('compact', self.compact)
        root.layout().setContentsMargins(*( (14, 12, 14, 10) if self.compact else (24, 20, 24, 16)))
        root.layout().setSpacing(7 if self.compact else 10)
        self.main_grid.setSpacing(8 if self.compact else 16)
        for panel in (self.institution_panel, self.credit_panel):
            panel.layout().setContentsMargins(*( (12, 10, 12, 10) if self.compact else (22, 18, 22, 16)))
        for _, item in self.institution_rows:
            item.note.setVisible(not self.compact)
            item.layout().setContentsMargins(0, 2 if self.compact else 4, 0, 2 if self.compact else 4)
        for item in (self.financing, self.short):
            item.compact = self.compact
            item.previous.setVisible(not self.compact)
        self.credit_grid.setHorizontalSpacing(14 if self.compact else 26)
        self.banner.setVisible(not self.compact)
        self.market_panel.setVisible(not self.compact)
        self.compact_market.setVisible(self.compact)
        self.dates.setMinimumWidth(140 if self.compact else 160)
        for button in (self.pin_btn, self.refresh_btn, self.previous_date_btn, self.next_date_btn):
            button.setFixedSize(32 if self.compact else 38, 32 if self.compact else 36)
        self.tabs.setVisible(not self.compact); self.scope.setVisible(not self.compact)
        self.export_btn.setVisible(not self.compact); self.credit_note.setVisible(not self.compact)
        self.compact_btn.setText('展開' if self.compact else '精簡視窗')
        for widget in [root, *root.findChildren(QWidget)]:
            widget.style().unpolish(widget); widget.style().polish(widget)
        self.render()
        self.arrange_panels()
        self.centralWidget().layout().activate()
        self.resize_for_mode()
        QTimer.singleShot(0, self.resize_for_mode)

    def resize_for_mode(self):
        self.resize(440 if self.compact else 1180, 470 if self.compact else 960)

    def pin(self, enabled):
        self.pin_btn.setText('📌' if enabled else '📍')
        self.pin_btn.setToolTip('已置頂 · 點擊取消' if enabled else '尚未置頂 · 點擊開啟')
        self.pin_btn.setAccessibleName('置頂：開啟' if enabled else '置頂：關閉')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled); self.show()

    def load(self):
        selected = self.dates.currentData()
        follow_latest = not self.rows or selected == self.rows[-1]['date']
        self.rows = history(self.path)
        self.dates.blockSignals(True); self.dates.clear()
        for row in reversed(self.rows):
            self.dates.addItem(row['date'], row['date'])
        index = 0 if follow_latest else self.dates.findData(selected)
        self.dates.setCurrentIndex(max(index, 0)); self.dates.blockSignals(False)
        self.render()
        if self.rows:
            latest = self.rows[-1]
            summary = f"{latest['date']} 外資 {money(latest.get('foreign_net'))} 億\n融資增減 {money(delta(latest, 'financing'))} 億／融券 {signed(delta(latest, 'short'))}"
            self.tray.setToolTip(summary); self.tray_summary.setText(summary)

    def render(self):
        index = self.dates.currentIndex()
        self.previous_date_btn.setEnabled(0 <= index < self.dates.count() - 1)
        self.next_date_btn.setEnabled(index > 0)
        selected = self.dates.currentData()
        row = next((r for r in self.rows if r['date'] == selected), {'sources': {}})
        sources = row['sources']
        missing = [title for key, title in (('institutions', '法人'), ('margin', '融資券')) if key not in sources]
        self.data_badge.setText('資料齊全' if not missing else '待補資料')
        self.data_badge.setStyleSheet(f"color:{'#88c0d0' if not missing else YELLOW}")
        if not self.rows:
            self.banner.setText('尚無資料，點「更新」下載官方盤後報表。')
        else:
            is_latest = selected == self.rows[-1]['date']
            self.banner.setText(('最新可用交易日' if is_latest else '歷史交易日') + f'  ·  台北今日 {today()}' + (f"  ·  尚缺{'、'.join(missing)}" if missing else '  ·  法人與融資券均已公布'))
        total = row.get('total_net')
        self.total_value.setText(yi_html(total))
        self.total_value.setStyleSheet(f'color:{color(total)}')
        self.total_value.setToolTip('尚未公布／下載' if total is None else f'{direction(total)} · {exact(total)} 元')
        for key, item in self.institution_rows:
            item.update_value(row, key)
        self.financing.update_value(row); self.short.update_value(row)
        close, change, rate = row.get('close'), row.get('index_change'), row.get('index_pct')
        turnover = row.get('turnover')
        self.market_values[0].setText('—' if close is None else f'{close:,.2f}')
        self.market_notes[0].setText('收盤點數')
        self.market_values[1].setText('—' if change is None else f'{change:+,.2f} 點')
        self.market_values[1].setStyleSheet(f'color:{color(change)}')
        self.market_notes[1].setText('—' if rate is None else f'{rate:+.2f}%')
        self.market_notes[1].setStyleSheet(f'color:{color(rate)}')
        self.market_values[2].setText(yi_html(turnover, signed_value=False))
        self.market_notes[2].setObjectName('detail')
        self.market_notes[2].hide()
        self.market_values[2].setToolTip('尚未公布' if turnover is None else f'{exact(turnover, False)} 元')
        rate_text = '—' if rate is None else f'{signed(rate, 2)}%'
        self.compact_market.setText('尚無大盤資料' if close is None else f'加權 {close:,.2f}　<span style="color:{color(rate)};font-weight:600">{rate_text}</span>　·　量 {money(turnover, False)} 億')
        self.compact_market.setToolTip(self.market_values[2].toolTip())
        self.data_badge.setToolTip(self.banner.text())
        visible = [r for r in self.rows if selected and r['date'] <= selected]
        for chart in self.charts:
            chart.update_data(visible)
        self.render_table()
        self.browser.setHtml(markdown_html(markdown(self.rows, row) if self.rows else markdown([])))

    def render_table(self):
        if not hasattr(self, 'table'):
            return
        full = self.units.currentIndex() == 1
        unit = '元' if full else '億'
        self.table.setHorizontalHeaderLabels(['日期'] + [f'{name}（{unit}）' for name in ('外資', '投信', '自營商', '合計', '融資增減')] + ['融券增減', '大盤 %', f'成交額（{unit}）'])
        self.table.setRowCount(len(self.rows))
        selected_index = None
        for i, row in enumerate(reversed(self.rows)):
            raw = [row.get(k) for k in ('foreign_net', 'trust_net', 'dealer_net', 'total_net')] + [delta(row, 'financing'), delta(row, 'short'), row.get('index_pct'), row.get('turnover')]
            values = [row['date']]
            for j, value in enumerate(raw):
                if j == 5:
                    values.append(exact(value))
                elif j == 6:
                    values.append(signed(value, 2))
                else:
                    values.append(exact(value, j != 7) if full else money(value, j != 7))
            for j, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment((Qt.AlignmentFlag.AlignLeft if j == 0 else Qt.AlignmentFlag.AlignRight) | Qt.AlignmentFlag.AlignVCenter)
                if j > 0:
                    if j < 8:
                        item.setForeground(QColor(color(raw[j-1])))
                    item.setToolTip('尚未公布' if raw[j-1] is None else f"{exact(raw[j-1]) if j != 7 else signed(raw[j-1], 2)} {'交易單位' if j == 6 else '%' if j == 7 else '元'}")
                self.table.setItem(i, j, item)
            if row['date'] == self.dates.currentData():
                selected_index = i
        if selected_index is not None:
            self.table.selectRow(selected_index)

    def shift_date(self, step):
        index = self.dates.currentIndex() + step
        if 0 <= index < self.dates.count():
            self.dates.setCurrentIndex(index)

    def select_table_date(self, row, column):
        self.dates.setCurrentIndex(self.dates.findData(self.table.item(row, 0).text()))

    def refresh(self):
        if self.worker is not None:
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText('⏳')
        self.refresh_btn.setToolTip('資料更新中…')
        self.worker = SyncWorker(self.path, configured_start(self.path))
        self.worker.progress.connect(self.status.setText)
        self.worker.result.connect(self.synced)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def synced(self, result):
        self.load()
        problems = result['errors'] + result['pending']
        if result['errors']:
            self.status.setText(f"部分更新失敗（{len(result['errors'])}），已保留本機資料；滑鼠移此查看原因。")
        elif result['pending']:
            self.status.setText("部分盤後資料尚未公布，稍後會再更新。")
        else:
            self.status.setText(f"更新完成 · {result['market_dates']} 個交易日 · 每 30 分鐘自動更新")
        self.status.setToolTip('\n'.join(problems) if problems else '下載成功；資料最新日期請見上方。')

    def worker_finished(self):
        self.worker.deleteLater(); self.worker = None
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText('🔄')
        self.refresh_btn.setToolTip('更新資料 · 每 30 分鐘自動更新')
        if self.quit_after:
            QApplication.instance().quit()

    def export_report(self):
        filename, _ = QFileDialog.getSaveFileName(self, "匯出台股報告", f"台股報告-{self.dates.currentData()}.html", "HTML (*.html);;Markdown (*.md)")
        if filename:
            try:
                export(self.path, filename, self.dates.currentData())
                QDesktopServices.openUrl(QUrl.fromLocalFile(filename))
            except OSError as exc:
                QMessageBox.warning(self, "匯出失敗", str(exc))

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show(); self.raise_(); self.activateWindow()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def closeEvent(self, event):
        if self.tray.isVisible():
            self.hide(); event.ignore()
        elif self.worker is not None:
            self.quit_after = True
            self.status.setText("更新結束後關閉…")
            event.ignore()
        else:
            event.accept()

    def quit_app(self):
        if self.worker is not None:
            self.quit_after = True
            self.status.setText("更新結束後結束程式…")
        else:
            QApplication.instance().quit()


def run(path=DEFAULT_DB, compact=False, screenshot=None):
    app = QApplication(sys.argv[:1])
    app.setApplicationName("台股數字核對"); app.setStyleSheet(STYLE); app.setWindowIcon(icon())
    path = Path(path).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    server_name = 'tw-stock-report-' + hashlib.sha256(str(path).encode()).hexdigest()[:24]
    if not screenshot:
        client = QLocalSocket()
        client.connectToServer(server_name)
        if client.waitForConnected(300):
            client.disconnectFromServer()
            return 0
    lock = QLockFile(str(path) + ".gui.lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "台股數字核對", "此資料庫的小工具已在執行，請點系統匣圖示開啟。")
        return 1
    window = Window(path, auto_refresh=not screenshot)
    server = QLocalServer()
    if not screenshot:
        QLocalServer.removeServer(server_name)
        if server.listen(server_name):
            def activate():
                connection = server.nextPendingConnection()
                if connection:
                    connection.close(); connection.deleteLater()
                window.showNormal(); window.raise_(); window.activateWindow()
            server.newConnection.connect(activate)
    if compact:
        window.toggle_compact()
    window.show()
    if screenshot:
        # 僅供無桌面環境驗證 UI，不啟動下載。
        window.timer.stop()
        def capture():
            window.grab().save(str(screenshot)); app.quit()
        QTimer.singleShot(200, capture)
    code = app.exec()
    lock.unlock()
    return code
