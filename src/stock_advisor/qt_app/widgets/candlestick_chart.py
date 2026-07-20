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

from ...domain import chart as geometry
from ...domain.models import DailyBar
from ..theme.tokens import load_tokens

# 版面比例：主图占七成，成交量占三成，中间留一条呼吸带。
_PRICE_RATIO = 0.70
_VOLUME_GAP = 8.0
_PADDING = 12.0
_READOUT_HEIGHT = 22.0
_CANDLE_MAX_WIDTH = 9.0
_MA_WINDOWS = (5, 20)


class CandlestickChart(QtWidgets.QWidget):
    """日线蜡烛图 + 均线 + 成交量，鼠标悬停显示十字光标与当根 OHLC。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._bars: list[DailyBar] = []
        self._title = ""
        self._hover = -1
        tokens = load_tokens()
        self._up = QtGui.QColor(tokens.colors["up_red"])
        self._down = QtGui.QColor(tokens.colors["down_green"])
        self._ink = QtGui.QColor(tokens.colors["ink"])
        self._grid = QtGui.QColor(tokens.state_colors["gridline"])
        self._ma_colors = [
            QtGui.QColor(tokens.colors["interactive"]),
            QtGui.QColor(tokens.colors["amber"]),
        ]
        self.setMinimumHeight(220)
        self.setMouseTracking(True)  # 不按键也要收到移动事件，否则 hover 不成立
        self.setAccessibleName("K线图")
        self.setAccessibleDescription(
            "日线蜡烛图，含 5 日与 20 日均线及成交量；鼠标悬停显示当日开高低收"
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
        return (
            f"{bar.date}　开 {_price(bar.open)}　高 {_price(bar.high)}　"
            f"低 {_price(bar.low)}　收 {_price(bar.close)}"
        )

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
        """返回主图区域 (left, right, top, height)；成交量区在其下方。"""
        left = _PADDING
        right = max(left + 1.0, self.width() - _PADDING)
        top = _PADDING + _READOUT_HEIGHT
        usable = max(1.0, self.height() - top - _PADDING)
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
        volume_height = max(1.0, self.height() - volume_top - _PADDING)
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
            QtCore.QPointF(x, self.height() - _PADDING),
        )

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
