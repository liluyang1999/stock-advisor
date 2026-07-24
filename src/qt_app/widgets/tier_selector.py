"""决策强度档位切换控件（REQ-003 / REQ-015 / WI-011 / WI-034）。

持有一次分析产出的缓存 `Measurement` 列表；用户切换 L1–L5 时，对**缓存**逐只重判并发出
`results_changed`，全程不接受 provider、不发起任何网络请求——这是 REQ-003"切档只重判缓存、
不联网"在 UI 层的落点。重判逻辑本身在框架无关的 `services.tier_switch`。

**形态是五段并排的分段按钮，不是下拉框**（WI-034）。这是老 Tkinter 版最强的交互识别点：五档一字排开
坐在墨蓝指挥带里，当前档翻成纸面色，用户一眼看到"自己在第几档、旁边还有几档"。换成下拉框虽然省地方，
却把这个对照关系藏了起来——而"五档对照"恰恰是这个产品的核心卖点（见 README 的决策强度光谱）。

切档时另发 `level_changed(level)` 供接线方做持久化。它与 `results_changed` 分开：后者带的是重判后
的结果列表，而「该把哪一档存进配置」只需要档位号本身。此处原有一层 `combo` 外观（把分段按钮伪装成
QComboBox），但下拉框那一版早已不存在，外观的三个方法只有一个真被用到，属纯粹的间接层，已移除。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from domain.models import LEVEL_NAMES, STANDARD_LEVEL, AnalysisResult, Measurement
from services.tier_switch import redecide_at_level
from ui.view_text import level_summary

from .cards import gap, label


def level_label(level: int) -> str:
    """档位按钮文案，沿用老版的 "L3标准" 形式——只有序号能让用户看出五档的先后。"""

    return f"L{level}{LEVEL_NAMES[level]}"


class TierSelector(QtWidgets.QWidget):
    """墨蓝指挥带：五档分段按钮 + 当前档位口径说明；切档即重判缓存并发信号。

    老版这条带子是整个界面最强的锚点，除了五个档位按钮，下面还常驻一行 `level_summary()`——
    「标准档 · 买入线 +25 / 卖出线 -25 · 风险预算 1% · 仓位上限 60%」。少了这行，用户就只能靠
    档位的名字猜自己切到了什么口径，而这恰恰是本产品的核心卖点。
    """

    results_changed = QtCore.Signal(object)  # list[AnalysisResult]
    level_changed = QtCore.Signal(int)  # 当前档位 1-5，供持久化

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._measurements: list[Measurement] = []
        self._levels = sorted(LEVEL_NAMES)  # [1,2,3,4,5]
        self._level = STANDARD_LEVEL

        # 指挥带外观由 QSS 的 role="command" 提供（墨蓝底 + 描边）。
        # WA_StyledBackground 是必须的：Qt 默认**不**为 QWidget 子类绘制样式表里的 background，
        # 只有 QFrame 之类自带绘制的部件才生效。少了这一行，墨蓝底就只在几个分段按钮上出现，
        # 整条带子仍是纸面色——正是重构前那张截图里"指挥带只剩五个按钮"的成因。
        self.setProperty("role", "command")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(gap(2), gap(1), gap(2), gap(1))
        column.setSpacing(gap(0))

        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(gap(1))
        layout.addStretch(1)
        layout.addWidget(QtWidgets.QLabel("决策强度"))

        # 分段之间不留缝：视觉上是一条连续的段带，而不是五个独立按钮。
        segments = QtWidgets.QHBoxLayout()
        segments.setSpacing(0)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[int, QtWidgets.QPushButton] = {}
        for level in self._levels:
            button = QtWidgets.QPushButton(level_label(level))
            button.setProperty("role", "segment")
            button.setCheckable(True)
            button.setChecked(level == STANDARD_LEVEL)
            # 每段自带可访问名：读屏要能报出"第几档、叫什么"，而不是只念一个"按钮"（REQ-017）。
            button.setAccessibleName(f"决策强度 {level_label(level)}")
            self._group.addButton(button, level)
            self._buttons[level] = button
            segments.addWidget(button)
        layout.addLayout(segments)
        layout.addStretch(1)
        column.addLayout(layout)

        # 档位口径说明：切档即刷新，让"我现在是什么标准"始终可见。
        self.level_hint = label(level_summary(self._level), "hint")
        self.level_hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.level_hint.setAccessibleName("当前决策强度口径")
        column.addWidget(self.level_hint)

        self._group.idClicked.connect(self._on_segment_clicked)

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
                self.level_changed.emit(level)
            self._emit_current()
        else:
            self._emit_current()  # 越界档位仍按 redecide 的 clamp 口径重判

    # --- 内部 ---

    def _on_segment_clicked(self, level: int) -> None:
        self._level = level
        self.level_changed.emit(level)
        self._emit_current()

    def _emit_current(self) -> None:
        level = self.current_level()
        self.level_hint.setText(level_summary(level))
        results: list[AnalysisResult] = [redecide_at_level(m, level) for m in self._measurements]
        self.results_changed.emit(results)
