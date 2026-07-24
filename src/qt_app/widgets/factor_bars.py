"""因子拆解条形图（REQ-004 / WI-035）——老 Tkinter 版 `_draw_factor_bars` 的 Qt 等价物。

每个因子一行：左边是改写成大白话的因子名，右边是一条以中线为零点、向左（利空/绿）或向右
（利多/红）生长的条，末尾标 `+18` / `-6` 这样的带号分数。红涨绿跌沿用 A 股本土配色。

为什么是发散条而不是表格：老版这块画布的作用是让人**一眼**看出"哪几项在拖后腿"。此前 Qt 版把
它做成了四列表格（因子/得分/判定/说明），信息虽在，但要逐行读数字才比较得出来，而且在窄面板里
被压成一条缝——重构前那张截图里的灰色细条就是它。

空态也画：老版会画四条占位骨架条，让这块地方在分析前就有形状，而不是一片空白。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from domain.models import FactorScore
from ui.view_text import friendly_factor_name

from ..theme.tokens import load_tokens

# 老版只画前 5 个因子——再多，每条就细到读不出来了。
MAX_BARS = 5
# 空态骨架条的比例，沿用老版 `_draw_empty_visual` 的取值。
_SKELETON = (0.62, 0.45, 0.70, 0.36)


class FactorBars(QtWidgets.QWidget):
    """把 `AnalysisResult.factor_scores` 画成一组以零为中心的发散条。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._factors: list[FactorScore] = []
        self._tokens = load_tokens()
        self.setMinimumSize(QtCore.QSize(260, 200))
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        # 图形本身没有文本，读屏只能靠可访问名认出它（REQ-017）。
        self.setAccessibleName("因子拆解条形图")

    def set_factors(self, factors: list[FactorScore]) -> None:
        self._factors = list(factors)[:MAX_BARS]
        self._refresh_accessible_text()
        self.update()

    def clear(self) -> None:
        self._factors = []
        self._refresh_accessible_text()
        self.update()

    def factor_count(self) -> int:
        """当前画了几根因子条。画布没有可查询的子部件，测试只能靠它断言"证据确实渲染了"。"""

        return len(self._factors)

    def _refresh_accessible_text(self) -> None:
        """读屏拿不到画布里的像素，所以把同样的内容以文本形式挂在可访问描述上（REQ-017）。"""

        if not self._factors:
            self.setAccessibleDescription("暂无因子")
            return
        self.setAccessibleDescription(
            "；".join(f"{friendly_factor_name(f.name)} {f.score:+d} 分" for f in self._factors)
        )

    # --- 绘制 ---

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802 - Qt 事件命名
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QtGui.QPainter) -> None:
        colour = self._tokens.colour
        width, height = self.width(), self.height()
        label_w = max(64, int(width * 0.24))
        value_w = 44
        left = label_w
        right = max(left + 20, width - value_w)
        centre = (left + right) / 2

        rows = self._factors or [None] * len(_SKELETON)
        top, bottom = 8, height - 22
        row_h = max(14.0, (bottom - top) / max(1, len(rows)))
        bar_h = min(18.0, row_h * 0.56)

        font = painter.font()
        font.setPointSizeF(self._tokens.font_points["caption"])
        painter.setFont(font)

        # 零点竖线：条从这里向两侧生长，没有它就看不出正负。
        painter.setPen(QtGui.QPen(QtGui.QColor(colour("card_border")), 1))
        painter.drawLine(
            QtCore.QPointF(centre, top), QtCore.QPointF(centre, top + row_h * len(rows))
        )

        for index, factor in enumerate(rows):
            y = top + row_h * index + (row_h - bar_h) / 2
            track = QtCore.QRectF(left, y, right - left, bar_h)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(colour("control")))
            painter.drawRoundedRect(track, 3, 3)

            if factor is None:
                # 空态骨架：不画分数，也不假装有数据。
                span = (right - centre) * _SKELETON[index]
                painter.setBrush(QtGui.QColor(colour("accent_soft")))
                painter.drawRoundedRect(QtCore.QRectF(centre, y, span, bar_h), 3, 3)
                continue

            limit = max(1, factor.max_abs_score)
            share = min(1.0, abs(factor.score) / limit)
            span = (right - centre) * share
            if factor.score > 0:
                bar = QtCore.QRectF(centre, y, span, bar_h)
                ink = colour("up_red")
            elif factor.score < 0:
                bar = QtCore.QRectF(centre - span, y, span, bar_h)
                ink = colour("down_green")
            else:
                bar = QtCore.QRectF(centre - 1, y, 2, bar_h)
                ink = colour("muted_ink")
            painter.setBrush(QtGui.QColor(ink))
            painter.drawRoundedRect(bar, 3, 3)

            painter.setPen(QtGui.QColor(colour("ink_soft")))
            painter.drawText(
                QtCore.QRectF(0, y - 2, label_w - 6, bar_h + 4),
                int(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter),
                friendly_factor_name(factor.name),
            )
            painter.setPen(QtGui.QColor(ink))
            painter.drawText(
                QtCore.QRectF(right + 4, y - 2, value_w - 6, bar_h + 4),
                int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
                f"{factor.score:+d}",
            )

        # 底部图例：哪边是利空、哪边是利多——不写出来，红绿就只是两种颜色。
        legend_y = height - 18
        painter.setPen(QtGui.QColor(colour("down_green")))
        painter.drawText(
            QtCore.QRectF(left, legend_y, centre - left - 4, 16),
            int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            "← 利空",
        )
        painter.setPen(QtGui.QColor(colour("up_red")))
        painter.drawText(
            QtCore.QRectF(centre + 4, legend_y, right - centre - 4, 16),
            int(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter),
            "利多 →",
        )
