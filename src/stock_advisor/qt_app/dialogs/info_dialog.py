"""帮助 / 策略信息窗（REQ-008 / REQ-016 / REQ-031 / WI-018）。

把 `view_text` 的帮助/策略段落渲染成只读富文本窗，底部常驻免责声明（REQ-031）。与 Tk 版
`show_help` / `show_strategy` 行为对齐：同一份 `build_help_sections` / `build_strategy_sections`
文案，Qt 侧只负责呈现、不复制文案；字体由应用级微软雅黑契约继承（REQ-016）。
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

from PySide6 import QtWidgets

from ...domain.models import CORE_DISCLAIMER
from ...ui.view_text import build_help_sections, build_strategy_sections


def sections_to_html(sections: Iterable[tuple[str, str]]) -> str:
    """[(标题, 正文)] → 富文本 HTML。正文里的换行转 <br>，全程转义，纯展示不含链接。"""

    parts: list[str] = []
    for title, body in sections:
        parts.append(f"<h3>{escape(title)}</h3>")
        parts.append(f"<p>{escape(body).replace(chr(10), '<br>')}</p>")
    return "\n".join(parts)


class SectionsDialog(QtWidgets.QDialog):
    """把 [(标题, 正文)] 段落渲染成只读富文本 + 常驻免责声明的信息窗。"""

    def __init__(
        self,
        title: str,
        sections: Iterable[tuple[str, str]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 640)
        layout = QtWidgets.QVBoxLayout(self)

        self.body = QtWidgets.QTextBrowser()
        self.body.setHtml(sections_to_html(sections))
        layout.addWidget(self.body)

        # REQ-031：信息窗底部常驻免责声明。
        self.disclaimer = QtWidgets.QLabel(CORE_DISCLAIMER)
        self.disclaimer.setWordWrap(True)
        layout.addWidget(self.disclaimer)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class HelpDialog(SectionsDialog):
    """使用说明 / 结果解释 / 数据说明（Tk 版 show_help 的 Qt 对等）。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("使用说明 / 结果解释 / 数据说明", build_help_sections(), parent)


class StrategyDialog(SectionsDialog):
    """策略说明 / 计算逻辑（Tk 版 show_strategy 的 Qt 对等）。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("策略说明 / 计算逻辑", build_strategy_sections(), parent)
