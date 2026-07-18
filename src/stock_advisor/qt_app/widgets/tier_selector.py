"""决策强度档位切换控件（REQ-003 / WI-011）。

持有一次分析产出的缓存 `Measurement` 列表；用户切换 L1–L5 时，对**缓存**逐只重判并发出
`results_changed`，全程不接受 provider、不发起任何网络请求——这是 REQ-003"切档只重判缓存、
不联网"在 UI 层的落点。重判逻辑本身在框架无关的 `services.tier_switch`。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...domain.models import LEVEL_NAMES, STANDARD_LEVEL, AnalysisResult, Measurement
from ...services.tier_switch import redecide_at_level


class TierSelector(QtWidgets.QWidget):
    """一个下拉框 + 缓存测量；切档即重判并发信号。"""

    results_changed = QtCore.Signal(object)  # list[AnalysisResult]

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._measurements: list[Measurement] = []
        self._levels = sorted(LEVEL_NAMES)  # [1,2,3,4,5]

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel("决策强度"))
        self.combo = QtWidgets.QComboBox()
        for level in self._levels:
            self.combo.addItem(LEVEL_NAMES[level], level)
        self.combo.setCurrentIndex(self._levels.index(STANDARD_LEVEL))
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.combo)
        layout.addStretch(1)

    def current_level(self) -> int:
        return int(self.combo.currentData())

    def set_measurements(self, measurements: list[Measurement]) -> None:
        """注入一次分析的缓存测量，并按当前档位立即发出重判结果。"""

        self._measurements = list(measurements)
        self._emit_current()

    def set_level(self, level: int) -> None:
        """程序化切档（等价于用户在下拉框里选）。"""

        if level in self._levels:
            self.combo.setCurrentIndex(self._levels.index(level))
        else:
            self._emit_current()  # 越界档位仍按 redecide 的 clamp 口径重判

    def _on_combo_changed(self, _index: int) -> None:
        self._emit_current()

    def _emit_current(self) -> None:
        level = self.current_level()
        results: list[AnalysisResult] = [redecide_at_level(m, level) for m in self._measurements]
        self.results_changed.emit(results)
