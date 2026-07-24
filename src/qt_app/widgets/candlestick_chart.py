"""K 线蜡烛图部件（REQ-004 / AC-003 / AC-004 / WI-027）。

**几何一律来自 `domain/chart.py`，本文件不算坐标。** 蜡烛的 x、影线端点、实体上下沿、均线、成交量
柱高、hover 命中，全部是纯函数算好的；这里只负责把算好的数拿 QPainter 画出来。这条分工不是洁癖：
坐标映射是可单测的纯逻辑，一旦在部件里重算一遍，就等于把它挪进了只能靠截图验证的地方。G-CORE 也
禁止反向依赖——`domain/chart.py` 不许 import PySide6。

配色沿用 A 股习惯（红涨绿跌），色值取自 tokens.json，不在此另抄一份。
"""

from __future__ import annotations

from decimal import Decimal

from PySide6 import QtCore, QtGui, QtWidgets

from domain import chart as geometry
from domain.models import DailyBar

from ..theme.tokens import load_tokens

# 版面比例：主图占七成，成交量占三成，中间留一条呼吸带。
_PRICE_RATIO = 0.70
_VOLUME_GAP = 8.0
_PADDING = 12.0
_READOUT_HEIGHT = 22.0
_CANDLE_MAX_WIDTH = 9.0
_PRICE_GUTTER = 48.0  # 右侧价格标尺槽：刻度文字画在这里，不压在蜡烛上
_DATE_AXIS_HEIGHT = 16.0  # 底部日期行：首/中/尾三个锚点
# 老 Tkinter 版画的是 MA5/MA10/MA20 三条（图标题也这么写）；此前 Qt 版只画了 5 与 20，
# 中期均线缺席，而「三线多头排列」正是引擎里均线结构因子的判据，图上却无从对照。
_MA_WINDOWS = (5, 10, 20)

# 右侧标尺槽里价签的位置：刻度价签与悬停收盘价签共用同一几何，提出来免得两处魔数各改各的。
_GUTTER_LABEL_ALIGN = int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)


def _gutter_label_rect(right: float, y: float) -> QtCore.QRectF:
    """右侧标尺槽内、垂直居中于 y 的价签矩形。"""

    return QtCore.QRectF(right + 4.0, y - 9.0, _PRICE_GUTTER - 8.0, 18.0)


class CandlestickChart(QtWidgets.QWidget):
    """日线蜡烛图 + 均线 + 成交量，鼠标悬停显示十字光标与当根 OHLC。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._bars: list[DailyBar] = []
        self._title = ""
        self._hover = -1
        tokens = load_tokens()
        # 一律走 tokens.colour() 取色，不直接下标 colors/state_colors——与另外两个自绘部件
        # （factor_bars/spectrum_strip）同一口径，调用方不必记住某个色值住在哪个组里
        # （gridline 就在 state_colors，直接 colors["gridline"] 会 KeyError）。
        self._up = QtGui.QColor(tokens.colour("up_red"))
        self._down = QtGui.QColor(tokens.colour("down_green"))
        self._ink = QtGui.QColor(tokens.colour("ink"))
        self._grid = QtGui.QColor(tokens.colour("gridline"))
        self._muted = QtGui.QColor(tokens.colour("muted_ink"))
        self._caption_font = QtGui.QFont(tokens.font_families[0])
        self._caption_font.setPointSizeF(tokens.font_points["caption"])
        # 三条均线各一色（短=蓝、中=琥珀、长=灰），色值取自 tokens，不另起一套图表调色板。
        self._ma_colors = [
            QtGui.QColor(tokens.colour("interactive")),
            QtGui.QColor(tokens.colour("amber")),
            QtGui.QColor(tokens.colour("muted_ink")),
        ]
        self.setMinimumHeight(220)
        self.setMouseTracking(True)  # 不按键也要收到移动事件，否则 hover 不成立
        self.setAccessibleName("K线图")
        self.setAccessibleDescription(
            "日线蜡烛图，含 5/10/20 日均线及成交量；鼠标悬停显示当日开高低收"
        )

    # --- 数据 ---

    def set_bars(self, bars: list[DailyBar], title: str = "") -> None:
        self._bars = list(bars)
        self._title = title
        self._hover = -1
        self.update()

    def clear(self) -> None:
        self.set_bars([], "")

    def bar_count(self) -> int:
        return len(self._bars)

    def hovered_index(self) -> int:
        return self._hover

    def hover_text(self) -> str:
        """当前悬停那根的读数；无悬停或无数据时为空串。测试与无障碍读屏都用这一条文本。"""
        if not (0 <= self._hover < len(self._bars)):
            return ""
        bar = self._bars[self._hover]
        text = (
            f"{bar.date}　开 {_price(bar.open)}　高 {_price(bar.high)}　"
            f"低 {_price(bar.low)}　收 {_price(bar.close)}"
        )
        # 涨跌幅与 OHLC 同格陈列——说明书承诺的读数是"开/高/低/收与涨跌幅"，缺一半就是失信。
        if bar.pct_change is not None:
            text += f"　涨跌 {bar.pct_change:+.2f}%"
        return text

    # --- 交互 ---

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self._set_hover(event.position().x())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._set_hover(None)
        super().leaveEvent(event)

    def _set_hover(self, x: float | None) -> None:
        if x is None or not self._bars:
            index = -1
        else:
            index = geometry.nearest_index(x, self._layout())
        if index != self._hover:
            self._hover = index
            self.update()

    # --- 绘制 ---

    def _plot_rect(self) -> tuple[float, float, float, float]:
        """返回主图区域 (left, right, top, height)；成交量区在其下方，日期行贴底。"""
        left = _PADDING
        right = max(left + 1.0, self.width() - _PADDING - _PRICE_GUTTER)
        top = _PADDING + _READOUT_HEIGHT
        usable = max(1.0, self.height() - top - _PADDING - _DATE_AXIS_HEIGHT)
        return left, right, top, usable * _PRICE_RATIO

    def _layout(self) -> list[dict]:
        left, right, top, height = self._plot_rect()
        return geometry.candle_layout(self._bars, left, right, top, height)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        try:
            if not self._bars:
                self._paint_empty(painter)
                return
            layout = self._layout()
            self._paint_axes(painter, layout)
            self._paint_candles(painter, layout)
            self._paint_moving_averages(painter)
            self._paint_volume(painter, layout)
            self._paint_crosshair(painter, layout)
            self._paint_readout(painter)
        finally:
            painter.end()

    def _paint_empty(self, painter: QtGui.QPainter) -> None:
        painter.setPen(self._ink)
        painter.drawText(
            self.rect(),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            "暂无历史数据" if not self._title else f"{self._title}：暂无历史数据",
        )

    def _candle_width(self, layout: list[dict]) -> float:
        if len(layout) < 2:
            return _CANDLE_MAX_WIDTH
        spacing = abs(layout[1]["x"] - layout[0]["x"])
        return max(1.0, min(_CANDLE_MAX_WIDTH, spacing * 0.7))

    def _paint_axes(self, painter: QtGui.QPainter, layout: list[dict]) -> None:
        """价格网格线 + 右侧刻度 + 底部日期锚点。先于蜡烛绘制，线在图形下面。

        刻度值来自 `nice_price_ticks`（整步进、全在界内），日期锚点来自 `axis_date_indices`
        （首/中/尾）；两者都是 domain/chart.py 的纯函数，这里只负责摆放文字。
        """

        left, right, top, height = self._plot_rect()
        lo, hi = geometry.price_bounds(self._bars)
        painter.setFont(self._caption_font)

        for tick in geometry.nice_price_ticks(lo, hi):
            y = geometry.price_to_y(tick, lo, hi, top, height)
            painter.setPen(QtGui.QPen(self._grid, 1.0))
            painter.drawLine(QtCore.QPointF(left, y), QtCore.QPointF(right, y))
            painter.setPen(self._muted)
            painter.drawText(_gutter_label_rect(right, y), _GUTTER_LABEL_ALIGN, f"{tick:g}")

        painter.setPen(self._muted)
        baseline = self.height() - _PADDING - _DATE_AXIS_HEIGHT
        for index in geometry.axis_date_indices(len(self._bars)):
            if not 0 <= index < len(layout):
                continue
            bar = self._bars[index]
            date_text = str(bar.date)[5:] if len(str(bar.date)) >= 10 else str(bar.date)
            align = QtCore.Qt.AlignmentFlag.AlignVCenter
            cell_x = layout[index]["x"]
            if index == 0:
                rect = QtCore.QRectF(cell_x, baseline, 96.0, _DATE_AXIS_HEIGHT)
                align |= QtCore.Qt.AlignmentFlag.AlignLeft
            elif index == len(self._bars) - 1:
                rect = QtCore.QRectF(cell_x - 96.0, baseline, 96.0, _DATE_AXIS_HEIGHT)
                align |= QtCore.Qt.AlignmentFlag.AlignRight
            else:
                rect = QtCore.QRectF(cell_x - 48.0, baseline, 96.0, _DATE_AXIS_HEIGHT)
                align |= QtCore.Qt.AlignmentFlag.AlignHCenter
            painter.drawText(rect, int(align), date_text)
        painter.setFont(self.font())

    def _paint_candles(self, painter: QtGui.QPainter, layout: list[dict]) -> None:
        width = self._candle_width(layout)
        for cell in layout:
            color = self._up if cell["up"] else self._down
            painter.setPen(QtGui.QPen(color, 1.0))
            x = cell["x"]
            painter.drawLine(
                QtCore.QPointF(x, cell["wick_top"]), QtCore.QPointF(x, cell["wick_bottom"])
            )
            # 实体高度可能为 0（开盘=收盘），此时画成一条横线才不会消失。
            body = max(1.0, cell["body_bottom"] - cell["body_top"])
            rect = QtCore.QRectF(x - width / 2, cell["body_top"], width, body)
            painter.fillRect(rect, color)

    def _paint_moving_averages(self, painter: QtGui.QPainter) -> None:
        left, right, top, height = self._plot_rect()
        lo, hi = geometry.price_bounds(self._bars)
        closes = [float(bar.close or 0.0) for bar in self._bars]
        count = len(self._bars)
        for window, color in zip(_MA_WINDOWS, self._ma_colors, strict=False):
            series = geometry.moving_average_series(closes, window)
            path = QtGui.QPainterPath()
            started = False
            for index, value in enumerate(series):
                if value is None:
                    started = False  # 断点：均线不足窗口的前段不连线，不能假装连续
                    continue
                point = QtCore.QPointF(
                    geometry.index_to_x(index, count, left, right),
                    geometry.price_to_y(value, lo, hi, top, height),
                )
                if started:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    started = True
            painter.setPen(QtGui.QPen(color, 1.2))
            painter.drawPath(path)

    def _paint_volume(self, painter: QtGui.QPainter, layout: list[dict]) -> None:
        _, _, top, price_height = self._plot_rect()
        volume_top = top + price_height + _VOLUME_GAP
        volume_height = max(1.0, self.height() - volume_top - _PADDING - _DATE_AXIS_HEIGHT)
        heights = geometry.volume_heights(self._bars, volume_height)
        width = self._candle_width(layout)
        baseline = volume_top + volume_height
        for cell, bar_height in zip(layout, heights, strict=False):
            color = self._up if cell["up"] else self._down
            rect = QtCore.QRectF(cell["x"] - width / 2, baseline - bar_height, width, bar_height)
            painter.fillRect(rect, color)
        painter.setPen(QtGui.QPen(self._grid, 1.0))
        painter.drawLine(
            QtCore.QPointF(_PADDING, baseline), QtCore.QPointF(self.width() - _PADDING, baseline)
        )

    def _paint_crosshair(self, painter: QtGui.QPainter, layout: list[dict]) -> None:
        if not (0 <= self._hover < len(layout)):
            return
        pen = QtGui.QPen(self._grid, 1.0, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        x = layout[self._hover]["x"]
        painter.drawLine(
            QtCore.QPointF(x, _PADDING + _READOUT_HEIGHT),
            QtCore.QPointF(x, self.height() - _PADDING - _DATE_AXIS_HEIGHT),
        )
        # 水平线钉在当根收盘价上，右侧标尺槽里同步给出该价位——横竖两线交在"这天收在哪"。
        bar = self._bars[self._hover]
        close = bar.close
        if close is not None:
            left, right, top, height = self._plot_rect()
            lo, hi = geometry.price_bounds(self._bars)
            y = geometry.price_to_y(float(close), lo, hi, top, height)
            painter.drawLine(QtCore.QPointF(left, y), QtCore.QPointF(right, y))
            painter.setFont(self._caption_font)
            painter.setPen(self._ink)
            painter.drawText(_gutter_label_rect(right, y), _GUTTER_LABEL_ALIGN, _price(close))
            painter.setFont(self.font())

    def _paint_readout(self, painter: QtGui.QPainter) -> None:
        painter.setPen(self._ink)
        text = self.hover_text() or self._title
        if not text:
            return
        painter.drawText(
            QtCore.QRectF(
                _PADDING, _PADDING / 2, max(1.0, self.width() - 2 * _PADDING), _READOUT_HEIGHT
            ),
            int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            text,
        )


def _price(value: Decimal | float | None) -> str:
    """价格读数。

    直接对 Decimal 套格式，不走 float：行情价是 2 位小数的 Decimal，转成 float 再格式化等于在
    展示环节引入一次二进制浮点误差，而这正是 ADR-0013 要避免的。缺值显示破折号而不是 0——
    把"没有数据"显示成"价格为零"是伪造。
    """
    if value is None:
        return "—"
    try:
        return f"{value:.2f}"
    except TypeError, ValueError:
        return "—"
