"""详细解释面板（REQ-004 / REQ-022 / REQ-031 / WI-035）。

老 Tkinter 版把 `build_detail_text()` 的整篇文字放进一个 `tk.Text`，再逐行按
`detail_line_tags()` 打标签着色：首行大标题、五个分节标题走口音蓝、要点缩进、因子行按分数正负
染红绿、风险行染警示色。Qt 侧用 `QTextEdit` + `QTextCharFormat` 表达同一套规则，**判定仍走
`view_format.detail_line_tags`**——着色规则只有一份，不在 Qt 侧另抄一遍。

顺带解决了重构前的一个实际问题：那时详情区是「证据强度标签 + 四列因子表 + 纯文本框 + 免责声明」
四件套挤在一个窄栏里，因子表被压成一条缝、文本框和邻居叠在一起。现在整篇解释就是一个可滚动的
文档，不再有互相争高度的兄弟部件。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from domain.models import AnalysisResult
from ui.view_format import detail_line_tags
from ui.view_text import build_detail_text

from ..theme.tokens import load_tokens

_PLACEHOLDER = "分析结果会显示在这里。"


class DetailView(QtWidgets.QTextEdit):
    """只读的富文本解释面板；`show_result` 渲染一只票的完整解释。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.WidgetWidth)
        self.setAccessibleName("详细解释")
        self._tokens = load_tokens()
        self._formats = self._build_formats()
        self.set_text(_PLACEHOLDER)

    def _build_formats(self) -> dict[str, QtGui.QTextCharFormat]:
        """把 `detail_line_tags` 的标签名映射成字符格式。标签集合与 Tk 版一一对应。"""

        colour = self._tokens.colour
        points = self._tokens.font_points

        def fmt(size: float, colour_hex: str, bold: bool = False) -> QtGui.QTextCharFormat:
            f = QtGui.QTextCharFormat()
            f.setFontPointSize(size)
            f.setForeground(QtGui.QColor(colour_hex))
            f.setFontWeight(QtGui.QFont.Weight.Bold if bold else QtGui.QFont.Weight.Normal)
            return f

        return {
            "headline": fmt(points["section"] + 1, colour("ink"), bold=True),
            "section": fmt(points["section"], colour("interactive"), bold=True),
            "bullet": fmt(points["body"], colour("ink_soft")),
            "positive": fmt(points["body"], colour("up_red")),
            "negative": fmt(points["body"], colour("down_green")),
            "risk": fmt(points["body"], colour("amber")),
            "muted": fmt(points["body"], colour("muted_ink")),
        }

    def _format_for(self, tags: tuple[str, ...]) -> tuple[QtGui.QTextCharFormat, bool]:
        """标签元组 → （字符格式, 是否缩进）。后出现的语义标签覆盖前面的基础标签。"""

        indent = "bullet" in tags or "risk" in tags
        chosen = self._formats["muted"]
        for tag in tags:
            if tag in self._formats:
                chosen = self._formats[tag]
        return chosen, indent

    def set_text(self, text: str) -> None:
        """按行着色地渲染一整篇文本。"""

        document = self.document()
        document.clear()
        cursor = QtGui.QTextCursor(document)
        lines = text.split("\n")
        first_seen = False
        for index, line in enumerate(lines):
            stripped = line.strip()
            is_first = not first_seen and bool(stripped)
            if is_first:
                first_seen = True
            char_format, indent = self._format_for(detail_line_tags(line, is_first))
            block_format = QtGui.QTextBlockFormat()
            block_format.setLeftMargin(18 if indent else 0)
            block_format.setTextIndent(0)
            block_format.setBottomMargin(6 if stripped else 2)
            if index:
                cursor.insertBlock(block_format, char_format)
            else:
                cursor.setBlockFormat(block_format)
                cursor.setCharFormat(char_format)
            cursor.insertText(line)
        self.moveCursor(QtGui.QTextCursor.MoveOperation.Start)

    def show_result(self, result: AnalysisResult, extra: str = "") -> None:
        """渲染一只票的完整解释；`extra` 追加仓位计划/回测等模块文本（老版也是同一篇里追加）。"""

        text = build_detail_text(result)
        if extra:
            text = f"{text}\n\n{extra}"
        self.set_text(text)

    def jump_to(self, heading: str) -> bool:
        """滚动到某个分节标题（老版详情导航「结论 / 依据 / 风险 / 操作」的落点）。

        返回是否找到——找不到就不动，不假装跳成功了。
        """

        found = self.find(heading, QtGui.QTextDocument.FindFlag.FindCaseSensitively)
        if not found:
            self.moveCursor(QtGui.QTextCursor.MoveOperation.Start)
            found = self.find(heading, QtGui.QTextDocument.FindFlag.FindCaseSensitively)
        if found:
            cursor = self.textCursor()
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.StartOfBlock)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
        return found

    def clear_detail(self, message: str = _PLACEHOLDER) -> None:
        self.set_text(message)
