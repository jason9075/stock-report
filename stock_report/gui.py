from __future__ import annotations

import hashlib
import math
import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QLockFile, QPointF, QRectF, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton,
    QSystemTrayIcon, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .data import DEFAULT_DB, configured_start, history, sync, today
from .render import markdown_html
from .report import YI, delta, exact, export, markdown, money, pct, ratio, signed
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


def tray_lines(row):
    if not row:
        return ['尚無數據']
    close, change, rate = row.get('close'), row.get('index_change'), row.get('index_pct')
    taiex = '尚未公布' if close is None else f'{close:,.2f}' + (f'（{change:+,.2f} / {rate:+.2f}%）' if change is not None and rate is not None else '')
    fin_bal, short_bal = row.get('financing_balance'), row.get('short_balance')
    fin = f"{money(delta(row, 'financing'))} 億" + (f"（餘額 {money(fin_bal, False)} 億）" if fin_bal is not None else '')
    short = f"{signed(delta(row, 'short'))} 單位" + (f"（餘額 {exact(short_bal, False)}）" if short_bal is not None else '')
    return [
        f"📅 {row['date']} 盤後數據",
        f"台指：{taiex}",
        f"外資：{money(row.get('foreign_net'))} 億",
        f"投信：{money(row.get('trust_net'))} 億",
        f"自營商：{money(row.get('dealer_net'))} 億",
        f"融資：{fin}",
        f"融券：{short}",
    ]


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


MA_COLORS = {5: '#ebcb8b', 10: '#b48ead', 20: '#81a1c1', 60: '#d08770'}
WINDOWS = {'day': 60, 'week': 52, 'month': 24}
WINDOW_NOTES = {'day': '最近 60 個交易日', 'week': '最近 52 週', 'month': '最近 24 個月'}


def bucket_key(day_text, interval):
    if interval == 'day':
        return day_text
    if interval == 'week':
        y, w, _ = date.fromisoformat(day_text).isocalendar()
        return f'{y}-W{w:02d}'
    return day_text[:7]


def flow_value(row, key):
    return delta(row, key) if key in ('financing', 'short') else row.get(key)


def build_series(rows, interval, kind, key=None):
    """依日／週／月分組。K 線取首開、最高、最低、末收；流量加總；餘額取期末。"""
    groups = {}
    for r in rows:
        groups.setdefault(bucket_key(r['date'], interval), []).append(r)
    series = []
    for bkey, items in groups.items():
        first, last = items[0]['date'], items[-1]['date']
        label = bkey if interval == 'month' else first if first == last else f'{first}~{last[5:]}'
        point = {'label': label, 'first': first, 'last': last}
        if kind == 'candle':
            bars = [r for r in items if all(r.get(k) is not None for k in ('open', 'high', 'low', 'close'))]
            if bars:
                point.update(o=bars[0]['open'], h=max(r['high'] for r in bars), l=min(r['low'] for r in bars), c=bars[-1]['close'])
            volumes = [r['turnover'] for r in items if r.get('turnover') is not None]
            point['v'] = sum(volumes) if volumes else None
        elif kind == 'line':
            values = [r[key] for r in items if r.get(key) is not None]
            point['value'] = values[-1] if values else None
        else:
            values = [v for v in (flow_value(r, key) for r in items) if v is not None]
            point['value'] = sum(values) if values else None
        series.append(point)
    return series


def moving_average(values, n):
    result = []
    for i in range(len(values)):
        window = values[max(0, i - n + 1):i + 1]
        result.append(sum(window) / n if i + 1 >= n and all(v is not None for v in window) else None)
    return result


def nice_step(raw, steps=(1, 2, 2.5, 5, 10)):
    mag = 10 ** math.floor(math.log10(max(raw, 1e-12)))
    return next(m * mag for m in steps if raw <= m * mag)


def nice_ticks(low, high, count=5):
    span = high - low
    if span <= 0:
        return [low]
    step = nice_step(span / count)
    tick = math.ceil(low / step) * step
    ticks = []
    while tick <= high + step * 1e-9:
        ticks.append(0.0 if abs(tick) < step * 1e-9 else tick)
        tick += step
    return ticks


def adaptive_log_ticks(low, high, height=170):
    """仿 TradingView 對數座標：依可視區間漲跌倍率與像素高度，動態調整各價位刻度間距。"""
    if high <= low or low <= 0:
        return [low]
    target = max(4, min(8, int(height / 24)))
    factor = (high / low) ** (1 / target) - 1
    steps = (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10)
    step0 = nice_step(low * factor, steps)
    cur = math.ceil(low / step0) * step0
    ticks = []
    flo, fhi = math.log(low), math.log(high)
    y_of = lambda v: height - (math.log(v) - flo) / ((fhi - flo) or 1) * height
    last_y = float('inf')
    while cur <= high * (1 + 1e-9):
        if cur >= low * (1 - 1e-9):
            yy = y_of(cur)
            if last_y - yy >= 18:
                ticks.append(0.0 if abs(cur) < step0 * 1e-9 else cur)
                last_y = yy
        step = nice_step(cur * factor, steps)
        cur = round((math.floor(cur / step + 1e-9) + 1) * step, 6)
    return ticks or [low, high]


def axis_label(point, interval):
    return point['label'] if interval == 'month' else point['first'][5:]


class TrendChart(QWidget):
    """K 線／柱狀／面積圖：含刻度格線、均線、對數座標與停留資訊卡。"""
    hovered = Signal(object)
    LEFT, RIGHT, TOP, BOTTOM = 64, 12, 30, 24

    def __init__(self, title, kind, key=None, scale=1):
        super().__init__()
        self.title, self.kind, self.key, self.scale = title, kind, key, scale
        self.full_series, self.full_mas = [], {}
        self.series, self.mas, self.hover_index, self.hover_y = [], {}, None, None
        self.interval, self.log, self.show_ma = 'day', False, True
        self.view_count, self.view_offset = None, 0
        self.x_scale, self.y_scale, self.y_shift = 1.0, 1.0, 0.0
        self.drag_mode, self.drag_origin = None, None
        self.periods = (5, 10, 20, 60) if kind == 'candle' else (5, 20)
        self.setMinimumHeight(210)
        self.setMouseTracking(True)

    # ── 資料 ──────────────────────────────────────────
    def value(self, point):
        return point.get('c') if self.kind == 'candle' else point.get('value')

    def default_count(self):
        total = max(len(self.full_series), 1)
        return total if self.kind == 'candle' else min(WINDOWS[self.interval], total)

    def update_data(self, rows, interval='day', log=False, show_ma=True):
        reset_window = self.interval != interval
        self.interval = interval
        self.log = log and self.kind in ('candle', 'line')
        self.show_ma = show_ma
        self.full_series = build_series(rows, interval, self.kind, self.key)
        values = [self.value(p) for p in self.full_series]
        for i, point in enumerate(self.full_series):
            point['prev'] = values[i - 1] if i else None
        self.full_mas = {n: moving_average(values, n) for n in self.periods}
        if reset_window or self.view_count is None:
            self.view_count, self.view_offset = self.default_count(), 0
            self.x_scale, self.y_scale, self.y_shift = 1.0, 1.0, 0.0
        self.apply_viewport()

    def apply_viewport(self):
        total = len(self.full_series)
        limit = max(total, 1)
        target = self.default_count() if self.view_count is None else self.view_count
        count = min(max(10, target), limit)
        max_offset = max(0, total - count)
        self.view_offset = max(0, min(self.view_offset, max_offset))
        end = total - self.view_offset
        start = max(0, end - count)
        self.series = self.full_series[start:end]
        self.mas = {n: m[start:end] for n, m in self.full_mas.items()}
        if self.hover_index is not None and self.hover_index >= len(self.series):
            self.hover_index = None
        self.update()

    def set_hover(self, index, hover_y=None):
        if self.hover_index != index or self.hover_y != hover_y:
            self.hover_index, self.hover_y = index, hover_y
            self.update()

    # ── 格式 ──────────────────────────────────────────
    def fmt(self, v, signed_value=None):
        if v is None:
            return '尚未公布'
        if self.key and self.key.startswith('put_call_'):
            return ratio(v)
        if self.kind == 'candle':
            return f'{v:,.2f}'
        if signed_value is None:
            signed_value = self.kind == 'bar'
        if self.scale > 1:
            return f'{money(v, signed_value)} 億'
        return f'{exact(round(v), signed_value)} 單位'

    def fmt_exact(self, v):
        if v is None or self.kind == 'candle':
            return None
        return f'{exact(round(v), self.kind == "bar")} 元' if self.scale > 1 else None

    def fmt_axis(self, v, step):
        if self.kind == 'candle':
            return f'{v:,.0f}'
        scaled, scaled_step = v / self.scale, step / self.scale
        digits = 0 if scaled_step >= 1 else 1 if scaled_step >= 0.1 else 2
        return f'{scaled:,.{digits}f}'

    # ── 互動（支援拖曳 X 軸、Y 軸個別調整刻度，雙擊軸線重設）──
    def plot_rect(self):
        return QRectF(self.LEFT, self.TOP, max(self.width() - self.LEFT - self.RIGHT, 1), max(self.height() - self.TOP - self.BOTTOM, 1))

    def price_rect(self):
        rect = self.plot_rect()
        return QRectF(rect.left(), rect.top(), rect.width(), rect.height() * (0.74 if self.kind == 'candle' else 1.0))

    def zone_at(self, pos):
        rect = self.plot_rect()
        if pos.x() < rect.left() and rect.top() <= pos.y() <= rect.bottom():
            return 'y'
        if pos.y() > rect.bottom() and pos.x() >= rect.left():
            return 'x'
        return 'plot'

    def update_cursor(self, pos):
        zone = self.zone_at(pos)
        if zone == 'y':
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif zone == 'x':
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            self.drag_mode = self.zone_at(pos)
            self.drag_origin = (pos.x(), pos.y(), self.x_scale, self.y_scale, self.y_shift, self.view_count, self.view_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_mode, self.drag_origin = None, None

    def mouseDoubleClickEvent(self, event):
        zone = self.zone_at(event.position())
        if zone in ('y', 'plot'):
            self.y_scale, self.y_shift = 1.0, 0.0
        if zone in ('x', 'plot'):
            self.x_scale, self.view_count, self.view_offset = 1.0, self.default_count(), 0
        self.apply_viewport()

    def mouseMoveEvent(self, event):
        pos = event.position()
        self.update_cursor(pos)
        if not self.series:
            return
        rect, price = self.plot_rect(), self.price_rect()
        slot = rect.width() / len(self.series)
        if self.drag_mode and self.drag_origin and (event.buttons() & Qt.MouseButton.LeftButton):
            ox, oy, ox_scale, oy_scale, oy_shift, o_count, o_offset = self.drag_origin
            dx, dy = pos.x() - ox, pos.y() - oy
            if self.drag_mode == 'y':
                self.y_scale = max(0.15, min(6.0, oy_scale * (1.007 ** dy)))
                self.update()
                return
            if self.drag_mode == 'x':
                self.x_scale = max(0.35, min(3.0, ox_scale * (1.005 ** dx)))
                base = o_count or self.default_count()
                self.view_count = round(max(10, min(max(len(self.full_series), 10), base * (1.005 ** dx))))
                self.apply_viewport()
                return
            delta_bars = int(dx / max(slot, 2))
            self.view_offset = o_offset + delta_bars
            if price.height() > 1:
                self.y_shift = oy_shift + dy / price.height() * oy_scale
            self.apply_viewport()
        index = int((pos.x() - rect.left()) // slot)
        index = max(0, min(len(self.series) - 1, index))
        hy = pos.y() if price.top() <= pos.y() <= price.bottom() else None
        self.set_hover(index, hy)
        self.hovered.emit(index)

    def wheelEvent(self, event):
        pos = event.position()
        delta_y = event.angleDelta().y()
        if self.zone_at(pos) == 'y':
            factor = 0.88 if delta_y > 0 else 1.14
            self.y_scale = max(0.15, min(6.0, self.y_scale * factor))
            self.update()
            event.accept()
            return
        if len(self.full_series) <= 10:
            return
        cur = self.view_count or self.default_count()
        step = max(2, round(cur * 0.12))
        if delta_y > 0:
            self.view_count = max(10, cur - step)
        elif delta_y < 0:
            self.view_count = min(len(self.full_series), cur + step)
        self.apply_viewport()
        event.accept()

    def leaveEvent(self, event):
        self.set_hover(None, None)
        self.hovered.emit(None)

    # ── 繪圖 ──────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        title_font = QFont(self.font()); title_font.setPixelSize(13); title_font.setBold(True)
        p.setFont(title_font); p.setPen(QColor('#d8dee9'))
        p.drawText(QRectF(0, 0, self.width(), 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        title_w = p.fontMetrics().horizontalAdvance(self.title)
        self.draw_legend(p, title_w + 14)
        values = [self.value(pt) for pt in self.series if self.value(pt) is not None]
        if not values:
            p.setPen(QColor(MUTED)); p.drawText(QRectF(0, 40, self.width(), 30), Qt.AlignmentFlag.AlignCenter, '等待資料'); return
        rect = self.plot_rect()
        n = len(self.series)
        slot = rect.width() / n
        cx = lambda i: rect.left() + (i + 0.5) * slot
        price = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * (0.74 if self.kind == 'candle' else 1.0))
        low, high = self.value_range()
        use_log = self.log and low > 0
        f = math.log if use_log else (lambda v: v)
        flo, fhi = f(low), f(high)
        y = lambda v: price.bottom() - (f(v) - flo) / ((fhi - flo) or 1) * price.height()
        small = QFont(self.font()); small.setPixelSize(11); p.setFont(small)
        # 水平格線與 Y 軸刻度（對數模式採 TradingView 式自適應間距，支援拖曳 Y 軸縮放刻度）
        tick_h = max(48, price.height() / max(self.y_scale, 0.35))
        ticks = adaptive_log_ticks(low, high, tick_h) if use_log else nice_ticks(low, high, max(2, int(tick_h / 34)))
        step = min((b - a for a, b in zip(ticks, ticks[1:])), default=high - low or 1)
        grid = QColor('#434c5e')
        for t in ticks:
            if not (low <= t <= high):
                continue
            ty = y(t)
            pen = p.pen(); pen.setColor(QColor('#4c566a') if t == 0 and self.kind == 'bar' else grid)
            pen.setStyle(Qt.PenStyle.SolidLine if t == 0 and self.kind == 'bar' else Qt.PenStyle.DotLine); pen.setWidthF(1.0); p.setPen(pen)
            p.drawLine(QPointF(price.left(), ty), QPointF(price.right(), ty))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, ty - 8, self.LEFT - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.fmt_axis(t, step))
        # X 軸刻度：由最新一筆往回等距，支援拖曳 X 軸調整密度
        every = max(1, round(math.ceil(n / 6) * self.x_scale))
        for i in range(n - 1, -1, -every):
            x = cx(i)
            pen = p.pen(); pen.setColor(grid); pen.setStyle(Qt.PenStyle.DotLine); p.setPen(pen)
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(x - 40, rect.bottom() + 4, 80, 16), Qt.AlignmentFlag.AlignCenter, axis_label(self.series[i], self.interval))
        # 外框
        pen = p.pen(); pen.setColor(QColor('#4c566a')); pen.setStyle(Qt.PenStyle.SolidLine); p.setPen(pen)
        p.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom()))
        p.drawLine(QPointF(rect.left(), rect.top()), QPointF(rect.left(), rect.bottom()))
        # 停留欄位底色
        if self.hover_index is not None and 0 <= self.hover_index < n:
            band = QColor('#4c566a'); band.setAlpha(70)
            p.fillRect(QRectF(rect.left() + self.hover_index * slot, rect.top(), slot, rect.height()), band)
        body = max(1.0, min(slot * 0.66, 14.0))
        p.save(); p.setClipRect(price)
        if self.kind == 'candle':
            self.draw_candles(p, cx, y, body)
        elif self.kind == 'bar':
            zero = y(0)
            for i, pt in enumerate(self.series):
                v = pt.get('value')
                if v is None:
                    continue
                c = QColor(RED if v > 0 else GREEN); c.setAlpha(215)
                top, bottom = sorted((y(v), zero))
                p.fillRect(QRectF(cx(i) - body / 2, top, body, max(bottom - top, 1)), c)
        else:
            self.draw_area(p, cx, y, price)
        if self.show_ma:
            self.draw_mas(p, cx, y)
        p.restore()
        if self.kind == 'candle':
            self.draw_volume(p, QRectF(rect.left(), price.bottom() + 8, rect.width(), rect.bottom() - price.bottom() - 8), cx, body, small)
        if self.hover_index is not None and 0 <= self.hover_index < n:
            x = cx(self.hover_index)
            pt = self.series[self.hover_index]
            pen = p.pen(); pen.setColor(QColor('#81a1c1')); pen.setStyle(Qt.PenStyle.DashLine); pen.setWidthF(1.0); p.setPen(pen)
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            # 水平準線與左側 Y 軸數值標籤
            pt_val = self.value(pt)
            if self.hover_y is not None and price.top() <= self.hover_y <= price.bottom():
                hy = self.hover_y
                ratio_y = (price.bottom() - hy) / max(price.height(), 1)
                hval = math.exp(flo + ratio_y * (fhi - flo)) if use_log else low + ratio_y * (high - low)
            elif pt_val is not None and (not use_log or pt_val > 0):
                hy = max(price.top(), min(price.bottom(), y(pt_val)))
                hval = pt_val
            else:
                hy, hval = None, None
            if hy is not None and hval is not None:
                p.drawLine(QPointF(price.left(), hy), QPointF(price.right(), hy))
                self.draw_y_badge(p, price, hy, self.fmt_axis(hval, step / 2))
            self.draw_x_badge(p, rect, x, axis_label(pt, self.interval))
            self.draw_card(p, rect, x)

    def value_range(self):
        values = []
        for pt in self.series:
            if self.kind == 'candle' and pt.get('h') is not None:
                values += [pt['h'], pt['l']]
            elif self.value(pt) is not None:
                values.append(self.value(pt))
        if self.kind != 'candle' and self.show_ma:
            for m in self.mas.values():
                values += [v for v in m if v is not None]
        low, high = min(values), max(values)
        if self.kind == 'bar':
            low, high = min(low, 0), max(high, 0)
        if self.log and low > 0 and self.kind != 'bar':
            ratio = (high / low) ** 0.05 if high > low else 1.008
            flo, fhi = math.log(low / ratio), math.log(high * ratio)
            fmid = (flo + fhi) / 2 + self.y_shift * (fhi - flo)
            fhalf = max((fhi - flo) / 2 * self.y_scale, 1e-4)
            return math.exp(fmid - fhalf), math.exp(fmid + fhalf)
        pad = (high - low) * 0.05 or abs(high) * 0.02 or 1
        low, high = low - pad, high + pad
        if self.kind == 'bar' and self.y_scale == 1.0 and self.y_shift == 0.0:
            low, high = min(low, 0), max(high, 0)
        mid = (low + high) / 2 + self.y_shift * (high - low)
        half = max((high - low) / 2 * self.y_scale, 1e-4)
        return mid - half, mid + half

    def draw_y_badge(self, p, price, hy, text):
        mono = QFont('DejaVu Sans Mono'); mono.setPixelSize(11); mono.setBold(True); p.setFont(mono)
        by = max(price.top() - 2, min(hy - 9, price.bottom() - 16))
        box = QRectF(2, by, self.LEFT - 5, 18)
        pen = p.pen(); pen.setColor(QColor('#88c0d0')); pen.setStyle(Qt.PenStyle.SolidLine); pen.setWidthF(1.0); p.setPen(pen)
        p.setBrush(QColor('#434c5e')); p.drawRoundedRect(box, 4, 4)
        p.drawLine(QPointF(box.right(), hy), QPointF(price.left(), hy))
        p.setPen(QColor('#eceff4'))
        p.drawText(QRectF(box.left() + 4, box.top(), box.width() - 8, box.height()), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

    def draw_x_badge(self, p, rect, x, text):
        mono = QFont('DejaVu Sans Mono'); mono.setPixelSize(11); mono.setBold(True); p.setFont(mono)
        bw = max(p.fontMetrics().horizontalAdvance(text) + 14, 48)
        bx = max(rect.left(), min(x - bw / 2, rect.right() - bw))
        box = QRectF(bx, rect.bottom() + 2, bw, 18)
        pen = p.pen(); pen.setColor(QColor('#88c0d0')); pen.setStyle(Qt.PenStyle.SolidLine); pen.setWidthF(1.0); p.setPen(pen)
        p.setBrush(QColor('#434c5e')); p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor('#eceff4'))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def draw_legend(self, p, x):
        p.setFont(QFont(self.font().family(), -1)); font = p.font(); font.setPixelSize(11); p.setFont(font)
        fm = p.fontMetrics()
        if self.kind == 'candle':
            p.setPen(QColor(MUTED)); text = '紅漲綠跌'
            p.drawText(QRectF(x, 0, 80, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x += fm.horizontalAdvance(text) + 12
        if self.show_ma:
            for n in self.periods:
                pen = p.pen(); pen.setColor(QColor(MA_COLORS[n])); pen.setWidthF(2); pen.setStyle(Qt.PenStyle.SolidLine); p.setPen(pen)
                p.drawLine(QPointF(x, 11), QPointF(x + 12, 11))
                p.setPen(QColor(MA_COLORS[n]))
                text = f'MA{n}'
                p.drawText(QRectF(x + 16, 0, 60, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
                x += 16 + fm.horizontalAdvance(text) + 10
        if self.log and self.kind != 'bar':
            p.setPen(QColor('#88c0d0'))
            p.drawText(QRectF(x, 0, 60, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 'LOG')

    def draw_candles(self, p, cx, y, body):
        for i, pt in enumerate(self.series):
            if pt.get('o') is None:
                continue
            up = pt['c'] >= pt['o']
            c = QColor(RED if up else GREEN)
            pen = p.pen(); pen.setColor(c); pen.setWidthF(1.0); pen.setStyle(Qt.PenStyle.SolidLine); p.setPen(pen)
            p.drawLine(QPointF(cx(i), y(pt['h'])), QPointF(cx(i), y(pt['l'])))
            top, bottom = sorted((y(pt['o']), y(pt['c'])))
            p.fillRect(QRectF(cx(i) - body / 2, top, body, max(bottom - top, 1.2)), c)

    def draw_volume(self, p, area, cx, body, font):
        volumes = [pt.get('v') for pt in self.series if pt.get('v')]
        if not volumes or area.height() < 10:
            return
        peak = max(volumes)
        p.setPen(QColor(MUTED)); p.setFont(font)
        p.drawText(QRectF(0, area.top() - 2, self.LEFT - 8, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f'{peak / YI:,.0f}億')
        p.drawText(QRectF(area.left() + 4, area.top() - 2, 80, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, '成交額')
        for i, pt in enumerate(self.series):
            v = pt.get('v')
            if not v:
                continue
            up = pt.get('o') is None or pt['c'] >= pt['o']
            c = QColor(RED if up else GREEN); c.setAlpha(120)
            h = v / peak * (area.height() - 12)
            p.fillRect(QRectF(cx(i) - body / 2, area.bottom() - h, body, h), c)

    def draw_area(self, p, cx, y, price):
        points = [(cx(i), y(pt['value'])) for i, pt in enumerate(self.series) if pt.get('value') is not None]
        if not points:
            return
        line = QPainterPath(QPointF(*points[0]))
        for x, yy in points[1:]:
            line.lineTo(x, yy)
        fill = QPainterPath(line); fill.lineTo(points[-1][0], price.bottom()); fill.lineTo(points[0][0], price.bottom()); fill.closeSubpath()
        gradient = QLinearGradient(0, price.top(), 0, price.bottom())
        top = QColor('#88c0d0'); top.setAlpha(90); bottom = QColor('#88c0d0'); bottom.setAlpha(8)
        gradient.setColorAt(0, top); gradient.setColorAt(1, bottom)
        p.fillPath(fill, gradient)
        pen = p.pen(); pen.setColor(QColor('#88c0d0')); pen.setWidthF(1.8); pen.setStyle(Qt.PenStyle.SolidLine); p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(line)

    def draw_mas(self, p, cx, y):
        p.setBrush(Qt.BrushStyle.NoBrush)
        for n, values in self.mas.items():
            path, active = QPainterPath(), False
            for i, v in enumerate(values):
                if v is None or (self.log and self.kind != 'bar' and v <= 0):
                    active = False; continue
                point = QPointF(cx(i), y(v))
                path.lineTo(point) if active else path.moveTo(point)
                active = True
            pen = p.pen(); pen.setColor(QColor(MA_COLORS[n])); pen.setWidthF(1.3); pen.setStyle(Qt.PenStyle.SolidLine); p.setPen(pen)
            p.drawPath(path)

    def card_rows(self, pt, i):
        rows = []
        if self.kind == 'candle':
            if pt.get('o') is None:
                rows.append(('收盤', '尚未公布', MUTED))
            else:
                change = None if pt.get('prev') is None else (pt['c'] / pt['prev'] - 1) * 100
                tone = color(change)
                rows += [('開盤', self.fmt(pt['o']), '#eceff4'), ('最高', self.fmt(pt['h']), '#eceff4'),
                         ('最低', self.fmt(pt['l']), '#eceff4'), ('收盤', self.fmt(pt['c']), tone)]
                if change is not None:
                    rows.append(('漲跌', f"{pt['c'] - pt['prev']:+,.2f}（{change:+.2f}%）", tone))
            if pt.get('v'):
                rows.append(('成交額', f"{pt['v'] / YI:,.2f} 億", '#eceff4'))
        else:
            v = pt.get('value')
            name = '期末餘額' if self.kind == 'line' else '合計' if self.interval != 'day' else '當日'
            rows.append((name, self.fmt(v), color(v) if self.kind == 'bar' else '#eceff4'))
            if (full := self.fmt_exact(v)):
                rows.append(('', full, MUTED))
        if self.show_ma:
            for n, values in self.mas.items():
                if values[i] is not None:
                    rows.append((f'MA{n}', self.fmt(values[i]), MA_COLORS[n]))
        return rows

    def draw_card(self, p, rect, x):
        pt = self.series[self.hover_index]
        rows = self.card_rows(pt, self.hover_index)
        head = QFont('DejaVu Sans Mono'); head.setPixelSize(12); head.setBold(True)
        body = QFont('DejaVu Sans Mono'); body.setPixelSize(11)
        p.setFont(head); head_w = p.fontMetrics().horizontalAdvance(pt['label'])
        p.setFont(body); fm = p.fontMetrics()
        line_h = 16
        columns = 2 if 26 + line_h * len(rows) + 4 > rect.height() - 12 else 1
        per_col = math.ceil(len(rows) / columns)
        label_w = max([fm.horizontalAdvance(r[0]) for r in rows] + [0])
        value_w = max([fm.horizontalAdvance(r[1]) for r in rows] + [0])
        col_w = label_w + 12 + value_w
        gap = 16
        width = max(head_w, col_w * columns + gap * (columns - 1)) + 20
        height = 26 + line_h * per_col + 4
        left = rect.left() + 8 if x > rect.center().x() else rect.right() - width - 8
        card = QRectF(left, rect.top() + 6, width, height)
        pen = p.pen(); pen.setColor(QColor('#4c566a')); pen.setWidthF(1.0); pen.setStyle(Qt.PenStyle.SolidLine); p.setPen(pen)
        p.setBrush(QColor(46, 52, 64, 235)); p.drawRoundedRect(card, 6, 6)
        p.setFont(head); p.setPen(QColor('#eceff4'))
        p.drawText(QRectF(card.left() + 10, card.top() + 5, width - 20, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, pt['label'])
        p.setFont(body)
        for k, (name, value, tone) in enumerate(rows):
            col, line = divmod(k, per_col)
            cell_left = card.left() + 10 + col * (col_w + gap)
            top = card.top() + 26 + line * line_h
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(cell_left, top, label_w, line_h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            p.setPen(QColor(tone))
            p.drawText(QRectF(cell_left, top, col_w, line_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value)


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
        self.scope = label('上市集中市場＋TXO  /  每日盤後', 'muted'); brand.addWidget(self.scope)
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

        self.put_call_summary = label('', 'muted', True)
        self.put_call_summary.setWordWrap(True)
        self.put_call_summary.setToolTip('臺指選擇權 TXO：賣權 ÷ 買權 × 100%；100%＝1 倍。週到期與各到期月份契約合併計算。')
        layout.addWidget(self.put_call_summary)

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
        self.trend_interval, self.trend_log, self.trend_ma = 'day', False, True
        self.trend_notes, self.interval_button_groups, self.log_buttons, self.ma_buttons, self.charts = [], [], [], [], []
        kline_trends = self.build_trend_tab([TrendChart('加權指數 K 線', 'candle')], log_toggle=True)
        inst_trends = self.build_trend_tab([
            TrendChart('外資買賣超 · 億元', 'bar', 'foreign_net', YI),
            TrendChart('投信買賣超 · 億元', 'bar', 'trust_net', YI),
            TrendChart('自營商買賣超 · 億元', 'bar', 'dealer_net', YI),
        ])
        margin_trends = self.build_trend_tab([
            TrendChart('融資餘額 · 億元', 'line', 'financing_balance', YI),
            TrendChart('融資增減 · 億元', 'bar', 'financing', YI),
            TrendChart('融券增減 · 交易單位', 'bar', 'short'),
        ], log_toggle=True)
        table_tools = QHBoxLayout(); table_tools.addWidget(label('逐日數據', 'section')); table_tools.addWidget(label('點選一列，查看該日明細', 'muted')); table_tools.addStretch()
        self.units = QComboBox(); self.units.addItems(['金額 · 億元', '完整金額 · 元']); self.units.currentIndexChanged.connect(self.render_table); table_tools.addWidget(self.units); ov.addLayout(table_tools)
        self.table = QTableWidget(0, 11); self.table.setMinimumHeight(190)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False); self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(37)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellClicked.connect(self.select_table_date); ov.addWidget(self.table, 1)
        self.tabs.addTab(overview, '歷史數據')
        self.tabs.addTab(kline_trends, '大盤 K 線')
        self.tabs.addTab(inst_trends, '三大法人趨勢')
        self.tabs.addTab(margin_trends, '融資券趨勢')
        self.tabs.addTab(self.build_trend_tab([
            TrendChart('Put/Call 未平倉量 · %', 'line', 'put_call_oi_pct'),
            TrendChart('Put/Call 成交量 · %', 'line', 'put_call_volume_pct'),
        ]), 'Put/Call 趨勢')
        self.browser = QTextBrowser(); self.browser.setOpenExternalLinks(True)
        self.browser.document().setDefaultStyleSheet('body{color:#d8dee9} h1,h2{color:#eceff4} a{color:#88c0d0} th{background:#434c5e} td,th{padding:8px} table{margin:12px 0}')
        self.tabs.addTab(self.browser, '完整報告與來源')
        bottom = QHBoxLayout(); self.status = label('本機紀錄可離線查看', 'muted'); self.status.setWordWrap(True); bottom.addWidget(self.status, 1)
        self.export_btn = QPushButton('匯出報告'); self.export_btn.clicked.connect(self.export_report); bottom.addWidget(self.export_btn); layout.addLayout(bottom)
        self.tray = QSystemTrayIcon(icon(), self); self.tray.setToolTip('台股數字核對')
        menu = QMenu()
        self.tray_actions = [menu.addAction('', self.show_window) for _ in range(7)]
        menu.addSeparator()
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

    def build_trend_tab(self, charts, log_toggle=False):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 12, 0, 8); layout.setSpacing(10)
        tools = QHBoxLayout()
        tools.addWidget(label('趨勢週期', 'section'))
        note = label('', 'muted')
        tools.addWidget(note); self.trend_notes.append(note)
        tools.addStretch()
        ma_btn = QPushButton('均線'); ma_btn.setCheckable(True); ma_btn.setChecked(self.trend_ma)
        ma_btn.setToolTip('顯示／隱藏移動平均線（MA）')
        ma_btn.clicked.connect(lambda checked: self.set_trend_ma(checked))
        tools.addWidget(ma_btn)
        self.ma_buttons.append(ma_btn)
        if log_toggle:
            log_btn = QPushButton('對數座標'); log_btn.setCheckable(True); log_btn.setChecked(self.trend_log)
            log_btn.setToolTip('以等比例顯示漲跌幅；僅套用於 K 線與餘額圖')
            log_btn.clicked.connect(lambda checked: self.set_trend_log(checked))
            tools.addWidget(log_btn)
            self.log_buttons.append(log_btn)
        tools.addSpacing(12)
        buttons = {}
        for key, text in (('day', '日線'), ('week', '週線'), ('month', '月線')):
            btn = QPushButton(text); btn.setCheckable(True); btn.setChecked(key == self.trend_interval)
            btn.clicked.connect(lambda _, k=key: self.set_trend_interval(k))
            tools.addWidget(btn)
            buttons[key] = btn
        self.interval_button_groups.append(buttons)
        layout.addLayout(tools)
        row = QHBoxLayout(); row.setSpacing(24)
        for chart in charts:
            chart.hovered.connect(self.sync_chart_hover)
            row.addWidget(chart)
            self.charts.append(chart)
        layout.addLayout(row, 1)
        return page

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
        lines = tray_lines(self.rows[-1] if self.rows else None)
        for action, text in zip(self.tray_actions, lines + [''] * len(self.tray_actions)):
            action.setText(text)
            action.setVisible(bool(text))
        self.tray.setToolTip('\n'.join(lines))

    def render(self):
        index = self.dates.currentIndex()
        self.previous_date_btn.setEnabled(0 <= index < self.dates.count() - 1)
        self.next_date_btn.setEnabled(index > 0)
        selected = self.dates.currentData()
        row = next((r for r in self.rows if r['date'] == selected), {'sources': {}})
        sources = row['sources']
        missing = [title for key, title in (('institutions', '法人'), ('margin', '融資券'), ('put_call', 'Put/Call')) if key not in sources]
        self.data_badge.setText('資料齊全' if not missing else '待補資料')
        self.data_badge.setStyleSheet(f"color:{'#88c0d0' if not missing else YELLOW}")
        if not self.rows:
            self.banner.setText('尚無資料，點「更新」下載官方盤後報表。')
        else:
            is_latest = selected == self.rows[-1]['date']
            self.banner.setText(('最新可用交易日' if is_latest else '歷史交易日') + f'  ·  台北今日 {today()}' + (f"  ·  尚缺{'、'.join(missing)}" if missing else '  ·  法人、融資券與 Put/Call 均已公布'))
        total = row.get('total_net')
        self.total_value.setText(yi_html(total))
        self.total_value.setStyleSheet(f'color:{color(total)}')
        self.total_value.setToolTip('尚未公布／下載' if total is None else f'{direction(total)} · {exact(total)} 元')
        for key, item in self.institution_rows:
            item.update_value(row, key)
        self.financing.update_value(row); self.short.update_value(row)
        self.put_call_summary.setText(f"TXO P/C　未平倉 {ratio(row.get('put_call_oi_pct'))}　·　成交量 {ratio(row.get('put_call_volume_pct'))}")
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
            chart.update_data(visible, self.trend_interval, self.trend_log, self.trend_ma)
        kline_note = f'全期間共 {len(self.charts[0].full_series)} 根 K 線（目前顯示 {len(self.charts[0].series)} 根）· 可拖曳 X／Y 軸個別調整刻度（雙擊重設）'
        other_note = f'{WINDOW_NOTES[self.trend_interval]} · 可拖曳 X／Y 軸個別調整刻度（雙擊重設）· 滾輪縮放／拖曳圖面平移'
        for i, note in enumerate(self.trend_notes):
            note.setText(kline_note if i == 0 else other_note)
        self.render_table()
        self.browser.setHtml(markdown_html(markdown(self.rows, row) if self.rows else markdown([])))

    def render_table(self):
        if not hasattr(self, 'table'):
            return
        full = self.units.currentIndex() == 1
        unit = '元' if full else '億'
        self.table.setHorizontalHeaderLabels(['日期'] + [f'{name}（{unit}）' for name in ('外資', '投信', '自營商', '合計', '融資增減')] + ['融券增減', '大盤 %', f'成交額（{unit}）', 'P/C 未平倉 %', 'P/C 成交量 %'])
        self.table.setRowCount(len(self.rows))
        selected_index = None
        for i, row in enumerate(reversed(self.rows)):
            raw = [row.get(k) for k in ('foreign_net', 'trust_net', 'dealer_net', 'total_net')] + [delta(row, 'financing'), delta(row, 'short'), row.get('index_pct'), row.get('turnover'), row.get('put_call_oi_pct'), row.get('put_call_volume_pct')]
            values = [row['date']]
            for j, value in enumerate(raw):
                if j >= 8:
                    values.append(ratio(value))
                elif j == 5:
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
                    item.setToolTip(ratio(raw[j-1]) if j >= 9 else '尚未公布' if raw[j-1] is None else f"{exact(raw[j-1]) if j != 7 else signed(raw[j-1], 2)} {'交易單位' if j == 6 else '%' if j == 7 else '元'}")
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

    def sync_chart_hover(self, index):
        sender = self.sender()
        for chart in self.charts:
            if chart is not sender:
                chart.set_hover(index)

    def set_trend_interval(self, interval):
        self.trend_interval = interval
        for buttons in self.interval_button_groups:
            for key, btn in buttons.items():
                btn.setChecked(key == interval)
        self.render()

    def set_trend_log(self, enabled):
        self.trend_log = enabled
        for btn in self.log_buttons:
            btn.setChecked(enabled)
        self.render()

    def set_trend_ma(self, enabled):
        self.trend_ma = enabled
        for btn in self.ma_buttons:
            btn.setChecked(enabled)
        self.render()

    def refresh(self):
        if self.worker is not None:
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText('⏳')
        self.refresh_btn.setToolTip('資料更新中…')
        self.worker = SyncWorker(self.path, configured_start(self.path))
        self.worker.progress.connect(self.sync_progress)
        self.worker.result.connect(self.synced)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def sync_progress(self, message):
        self.status.setText(message)
        if '三大法人' in message:
            self.load()

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

    def show_window(self):
        self.show(); self.raise_(); self.activateWindow()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show_window()

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


def run(path=DEFAULT_DB, compact=False, screenshot=None, start_in_tray=False):
    app = QApplication(sys.argv[:1])
    app.setApplicationName("台股數字核對"); app.setStyleSheet(STYLE); app.setWindowIcon(icon())
    path = Path(path).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    server_name = 'tw-stock-report-' + hashlib.sha256(str(path).encode()).hexdigest()[:24]
    if not screenshot:
        client = QLocalSocket()
        client.connectToServer(server_name)
        if client.waitForConnected(300):
            client.write(b'tray' if start_in_tray else b'show')
            client.waitForBytesWritten(300)
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
            def accept_connection():
                connection = server.nextPendingConnection()
                if connection:
                    def activate():
                        message = bytes(connection.readAll())
                        if message == b'show':
                            window.showNormal(); window.raise_(); window.activateWindow()
                        connection.disconnectFromServer()
                    connection.readyRead.connect(activate)
                    connection.disconnected.connect(connection.deleteLater)
                    if connection.bytesAvailable():
                        activate()
            server.newConnection.connect(accept_connection)
    if compact:
        window.toggle_compact()
    app.setQuitOnLastWindowClosed(not window.tray.isVisible())
    if screenshot or not start_in_tray or not window.tray.isVisible():
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
