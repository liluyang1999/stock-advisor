"""六宫格策略预设选择器（REQ-002 / WI-035）——老 Tkinter 版 `_build_screener_tab` 的预设格。

老版把六个策略摆成 2 行 × 3 列的方格，选中的那格翻成实心口音蓝、白字；其余是暖白底灰字。
六个策略名一次全部在眼前，用户能直接比较"我要动量还是要低估值"。此前 Qt 版把它压成一个下拉框，
六选一变成了"先点开才知道有什么"，而选股页的第一个决定恰恰就是选策略。

对外仍暴露一套 `QComboBox` 形状的接口（`count()` / `currentData()` / `findData()` /
`setCurrentIndex()` / `currentIndexChanged`），这样接线方（选股页的持久化）不必区分两种控件——
与 `TierSelector._SegmentedFacade` 同一手法。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from domain.presets import PRESETS

from .cards import gap

# 每行三格，两行放下六个预设——老版的网格形状。
_COLUMNS = 3


class PresetGrid(QtWidgets.QWidget):
    """2×3 的策略预设方格；选中项以实心口音色标出。"""

    currentIndexChanged = QtCore.Signal(int)  # noqa: N815 - 对齐 QComboBox 命名

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._presets = list(PRESETS)
        self._index = 0

        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(gap(0))
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QtWidgets.QPushButton] = []
        for index, preset in enumerate(self._presets):
            button = QtWidgets.QPushButton(preset.name)
            button.setProperty("role", "toggle")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setAccessibleName(f"筛选预设 {preset.name}")
            button.setToolTip(preset.description)
            self._group.addButton(button, index)
            self._buttons.append(button)
            grid.addWidget(button, index // _COLUMNS, index % _COLUMNS)
        for column in range(_COLUMNS):
            grid.setColumnStretch(column, 1)  # 三列等宽，与老版的 uniform 网格一致

        self._group.idClicked.connect(self._on_clicked)

    # --- QComboBox 形状的接口 ---

    def count(self) -> int:
        return len(self._presets)

    def currentData(self) -> str:  # noqa: N802 - 对齐 QComboBox 命名
        return self._presets[self._index].key

    def findData(self, key: object) -> int:  # noqa: N802 - 对齐 QComboBox 命名
        """按 preset key 找下标；找不到返回 -1（与 QComboBox 一致）。"""

        for index, preset in enumerate(self._presets):
            if preset.key == key:
                return index
        return -1

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - 对齐 QComboBox 命名
        if 0 <= index < len(self._presets) and index != self._index:
            self._index = index
            self._buttons[index].setChecked(True)
            self.currentIndexChanged.emit(index)

    def _on_clicked(self, index: int) -> None:
        self._index = index
        self.currentIndexChanged.emit(index)
