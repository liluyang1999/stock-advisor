"""决策强度光谱条（REQ-003 / REQ-015 / WI-035）——老 Tkinter 版 `_draw_spectrum_strip` 的等价物。

五个等宽圆角格子并排，每格两行：档位名（当前档带 ●）与该档给出的结论（买入 / 卖出 / 观望）。
格子按结论上色：买入=淡红底红字、卖出=淡绿底绿字、观望=米灰底灰字；**当前档额外描一圈口音色边**。

这是产品的核心卖点——同一只票在五档下分别是什么结论、在哪一档翻转，一眼看完。重构前 Qt 版把它
退化成一行 `▸标准:HOLD` 的纯文字，五档的对照关系就此消失（那行字正是用户截图里挤在右上角的
那一串）。

切档只对缓存的 `Measurement` 重判，不联网（REQ-003）——本部件纯展示，不碰数据。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from domain.models import SpectrumCell

from ..theme.tokens import load_tokens

# 结论 → （底色 token, 字色 token）。红涨绿跌，与结果表的行底色同源。
_ACTION_STYLE = {
    "BUY": ("buy_row", "up_red"),
    "SELL": ("sell_row", "down_green"),
    "HOLD": ("hold_row", "muted_ink"),
}
_ACTION_TEXT = {"BUY": "买入", "SELL": "卖出", "HOLD": "观望"}


class SpectrumStrip(QtWidgets.QWidget):
    """把 `domain.policy.spectrum()` 的五个 `SpectrumCell` 画成一条对照带。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._cells: list[SpectrumCell] = []
        self._tokens = load_tokens()
        self.setMinimumHeight(64)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.setAccessibleName("决策强度光谱")
        self.setAccessibleDescription("五档结论待显示")

    def set_cells(self, cells: list[SpectrumCell]) -> None:
        self._cells = list(cells)
        self.setAccessibleDescription(
            "；".join(
                f"{c.name}档 {_ACTION_TEXT.get(str(c.action), str(c.action))}"
                + ("（当前）" if c.is_current else "")
                for c in self._cells
            )
            or "五档结论待显示"
        )
        self.update()

    def clear(self) -> None:
        self._cells = []
        self.setAccessibleDescription("五档结论待显示")
        self.update()

    def cells(self) -> list[SpectrumCell]:
        """当前画出的五档格子。同上：画布无子部件，测试靠它断言五档都在、当前档标出来了。"""

        return list(self._cells)

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802 - Qt 命名
        return QtCore.QSize(560, 68)

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
        font = painter.font()

        if not self._cells:
            painter.setPen(QtGui.QColor(colour("muted_ink")))
            font.setPointSizeF(self._tokens.font_points["caption"])
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
                "五档结论待显示",
            )
            return

        gap = 6
        count = len(self._cells)
        usable = self.width() - gap * (count - 1)
        cell_w = usable / count
        top, bottom = 4, self.height() - 4

        for index, cell in enumerate(self._cells):
            x = index * (cell_w + gap)
            box = QtCore.QRectF(x, top, cell_w, bottom - top)
            fill_token, ink_token = _ACTION_STYLE.get(str(cell.action), ("hold_row", "muted_ink"))
            painter.setBrush(QtGui.QColor(colour(fill_token)))
            if cell.is_current:
                painter.setPen(QtGui.QPen(QtGui.QColor(colour("interactive")), 2))
            else:
                painter.setPen(QtGui.QPen(QtGui.QColor(colour(fill_token)), 1))
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), 6, 6)

            ink = QtGui.QColor(colour(ink_token))
            painter.setPen(ink)
            font.setPointSizeF(self._tokens.font_points["caption"])
            font.setBold(True)
            painter.setFont(font)
            name = f"{cell.name} ●" if cell.is_current else cell.name
            painter.drawText(
                QtCore.QRectF(box.x(), box.y() + 6, box.width(), box.height() / 2 - 4),
                int(QtCore.Qt.AlignmentFlag.AlignCenter),
                name,
            )
            font.setBold(False)
            painter.setFont(font)
            painter.drawText(
                QtCore.QRectF(
                    box.x(), box.y() + box.height() / 2, box.width(), box.height() / 2 - 6
                ),
                int(QtCore.Qt.AlignmentFlag.AlignCenter),
                _ACTION_TEXT.get(str(cell.action), str(cell.action)),
            )
