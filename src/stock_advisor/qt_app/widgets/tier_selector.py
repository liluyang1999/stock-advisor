"""决策强度档位切换控件（REQ-003 / REQ-015 / WI-011 / WI-034）。

持有一次分析产出的缓存 `Measurement` 列表；用户切换 L1–L5 时，对**缓存**逐只重判并发出
`results_changed`，全程不接受 provider、不发起任何网络请求——这是 REQ-003"切档只重判缓存、
不联网"在 UI 层的落点。重判逻辑本身在框架无关的 `services.tier_switch`。

**形态是五段并排的分段按钮，不是下拉框**（WI-034）。这是老 Tkinter 版最强的交互识别点：五档一字排开
坐在墨蓝指挥带里，当前档翻成纸面色，用户一眼看到"自己在第几档、旁边还有几档"。换成下拉框虽然省地方，
却把这个对照关系藏了起来——而"五档对照"恰恰是这个产品的核心卖点（见 README 的决策强度光谱）。

`combo` 属性保留为分段按钮组的兼容外观（`currentIndexChanged` 信号 + `currentData()`），
这样接线方（individual_page 的持久化）不必区分两种控件。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...domain.models import LEVEL_NAMES, STANDARD_LEVEL, AnalysisResult, Measurement
from ...services.tier_switch import redecide_at_level


class TierSelector(QtWidgets.QWidget):
    """五档分段按钮 + 缓存测量；切档即重判并发信号。"""

    results_changed = QtCore.Signal(object)  # list[AnalysisResult]

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._measurements: list[Measurement] = []
        self._levels = sorted(LEVEL_NAMES)  # [1,2,3,4,5]
        self._level = STANDARD_LEVEL

        # 指挥带外观由 QSS 的 role="command" 提供（墨蓝底 + 描边）。
        self.setProperty("role", "command")
        layout = QtWidgets.QHBoxLayout(self)
        spacing = 8
        layout.setContentsMargins(spacing + 4, spacing, spacing + 4, spacing)
        layout.setSpacing(spacing)
        layout.addWidget(QtWidgets.QLabel("决策强度"))

        # 分段之间不留缝：相邻按钮共享 1px 描边，视觉上是一条连续的段带。
        segments = QtWidgets.QHBoxLayout()
        segments.setSpacing(0)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[int, QtWidgets.QPushButton] = {}
        for level in self._levels:
            button = QtWidgets.QPushButton(LEVEL_NAMES[level])
            button.setProperty("role", "segment")
            button.setCheckable(True)
            button.setChecked(level == STANDARD_LEVEL)
            # 每段自带可访问名：读屏要能报出"第几档、叫什么"，而不是只念一个"按钮"（REQ-017）。
            button.setAccessibleName(f"决策强度 {LEVEL_NAMES[level]}")
            self._group.addButton(button, level)
            self._buttons[level] = button
            segments.addWidget(button)
        layout.addLayout(segments)
        layout.addStretch(1)

        self._group.idClicked.connect(self._on_segment_clicked)

        # 兼容外观：接线方按下拉框的接口用它，不必知道内部是分段按钮。
        self.combo = _SegmentedFacade(self)

    # --- 对外接口 ---

    def current_level(self) -> int:
        return self._level

    def set_measurements(self, measurements: list[Measurement]) -> None:
        """注入一次分析的缓存测量，并按当前档位立即发出重判结果。"""

        self._measurements = list(measurements)
        self._emit_current()

    def set_level(self, level: int) -> None:
        """程序化切档（等价于用户点某一段）。"""

        if level in self._levels:
            if level != self._level:
                self._level = level
                self._buttons[level].setChecked(True)
                self.combo.currentIndexChanged.emit(self._levels.index(level))
            self._emit_current()
        else:
            self._emit_current()  # 越界档位仍按 redecide 的 clamp 口径重判

    # --- 内部 ---

    def _on_segment_clicked(self, level: int) -> None:
        self._level = level
        self.combo.currentIndexChanged.emit(self._levels.index(level))
        self._emit_current()

    def _emit_current(self) -> None:
        level = self.current_level()
        results: list[AnalysisResult] = [redecide_at_level(m, level) for m in self._measurements]
        self.results_changed.emit(results)


class _SegmentedFacade(QtCore.QObject):
    """让分段按钮组对外长得像一个 QComboBox。

    只暴露接线方真正用到的两件事：`currentIndexChanged` 信号与 `currentData()`。这样把下拉框换成
    分段按钮时，持久化那条线（individual_page 存档位）一个字都不用改。
    """

    currentIndexChanged = QtCore.Signal(int)

    def __init__(self, owner: TierSelector) -> None:
        super().__init__(owner)
        self._owner = owner

    def currentData(self) -> int:
        return self._owner.current_level()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - 对齐 QComboBox 命名
        levels = self._owner._levels
        if 0 <= index < len(levels):
            self._owner.set_level(levels[index])
