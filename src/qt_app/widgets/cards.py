"""卡片、分节标题、指标条、空态步骤——老 Tkinter 版的结构语言（WI-035）。

老版每一块内容都住在同一种卡片里：一个涂描边色的外层 Frame（padx/pady=1）套一个涂填充色的
内层 Frame，顶部是「标题（粗）+ 说明（灰小字）」的表头条，下面一条 1px 分隔线，再往下才是正文。
整个界面的秩序感几乎全部来自这一个重复出现的形状。

Qt 版把它收成一个 `Card`：外观交给 QSS 的 `QFrame[role="card"]`（border + background 一句话就是
老版那两层 Frame），结构交给这里。页面因此只需要说"我要一张标题叫 X 的卡"，而不是每次重新拼
一遍表头、分隔线和留白——重构前五个页面正是各自手搓 QVBoxLayout，所以没有一处长得一样。

尺寸一律取自 tokens，不写死数字。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..theme.tokens import load_tokens


def gap(index: int = 1) -> int:
    """spacing_dip 的第 index 档（0=8, 1=12, 2=16, 3=24, 4=32）。"""

    scale = load_tokens().spacing_dip
    return scale[min(index, len(scale) - 1)]


def divider(
    orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
) -> QtWidgets.QFrame:
    """1px 分隔线——老版用一个只有 1px 厚的 Frame 涂 BORDER_SOFT 实现，这里等价。"""

    line = QtWidgets.QFrame()
    line.setProperty("role", "divider")
    if orientation is QtCore.Qt.Orientation.Horizontal:
        line.setFixedHeight(1)
        line.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
    else:
        line.setFixedWidth(1)
        line.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Expanding
        )
    return line


def label(text: str, role: str | None = None, wrap: bool = False) -> QtWidgets.QLabel:
    """带 role 的 QLabel。role 对应 QSS 里的文字层级：

    title / section / hint / summary / overview / value / step / alert。
    """

    item = QtWidgets.QLabel(text)
    if role is not None:
        item.setProperty("role", role)
    item.setWordWrap(wrap)
    return item


class Card(QtWidgets.QFrame):
    """一张内容卡：可选的「标题 + 说明」表头条、1px 分隔线，以及供页面填充的正文区。

    没有标题时就是一张纯粹的带描边容器（例如空态卡）。`head` 右侧可以继续挂按钮/菜单——老版的
    结果区就是把「加入自选 / 复制 / 更多」挂在「研究结果」标题的同一行右端。
    """

    def __init__(
        self,
        title: str | None = None,
        hint: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        pad = gap(2)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(pad, gap(1), pad, gap(1))
        outer.setSpacing(gap(0))

        self.title_label: QtWidgets.QLabel | None = None
        self.hint_label: QtWidgets.QLabel | None = None
        self._head_row: QtWidgets.QHBoxLayout | None = None

        if title is not None:
            head = QtWidgets.QWidget()
            head.setProperty("role", "card-head")
            row = QtWidgets.QHBoxLayout(head)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(gap(1))
            text = QtWidgets.QVBoxLayout()
            text.setSpacing(gap(0) // 2)
            self.title_label = label(title, "section")
            text.addWidget(self.title_label)
            if hint is not None:
                self.hint_label = label(hint, "hint", wrap=True)
                text.addWidget(self.hint_label)
            row.addLayout(text, 1)
            self._head_row = row
            outer.addWidget(head)
            outer.addWidget(divider())

        self._body = QtWidgets.QVBoxLayout()
        self._body.setContentsMargins(0, gap(0), 0, 0)
        self._body.setSpacing(gap(1))
        outer.addLayout(self._body, 1)

    def body(self) -> QtWidgets.QVBoxLayout:
        """正文区布局，页面往里塞内容。"""

        return self._body

    def add_head_widget(self, widget: QtWidgets.QWidget) -> None:
        """把一个控件挂到表头条右端（老版的「加入自选 / 复制 / 更多」就在这个位置）。"""

        if self._head_row is None:
            raise ValueError("这张卡没有表头条：构造时必须给 title 才有地方挂控件")
        self._head_row.addWidget(widget, 0, QtCore.Qt.AlignmentFlag.AlignTop)

    def set_hint(self, text: str) -> None:
        if self.hint_label is not None:
            self.hint_label.setText(text)

    def hint_text(self) -> str:
        """当前副标题文本；没有表头条时为空串。测试与联动逻辑都读这一处。"""

        return self.hint_label.text() if self.hint_label is not None else ""


class StatStrip(QtWidgets.QWidget):
    """等宽指标条：老版「当前股票摘要」的 方向 / 仓位 / 把握 / 波动 四格。

    每格是「小灰标题 + 粗大数值」，格与格之间一条 1px 竖线。值可以带自己的颜色（方向那一格
    会随买/卖/观望换成红/绿/灰），所以 `set_value` 收一个可选的色值。
    """

    def __init__(self, titles: list[str], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: dict[str, QtWidgets.QLabel] = {}

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        for index, title in enumerate(titles):
            if index:
                row.addWidget(divider(QtCore.Qt.Orientation.Vertical))
            cell = QtWidgets.QWidget()
            column = QtWidgets.QVBoxLayout(cell)
            column.setContentsMargins(gap(1), gap(0), gap(1), gap(0))
            column.setSpacing(2)
            caption = label(title, "hint")
            caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            value = label("—", "value")
            value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            # 读屏要能把"这个数是什么"读出来，而不是只念一个孤零零的数字（REQ-017）。
            value.setAccessibleName(title)
            column.addWidget(caption)
            column.addWidget(value)
            self._values[title] = value
            row.addWidget(cell, 1)

    def set_value(self, title: str, text: str, colour: str | None = None) -> None:
        item = self._values.get(title)
        if item is None:
            return
        item.setText(text)
        item.setStyleSheet(f"color: {colour};" if colour else "")

    def clear(self, placeholder: str = "—") -> None:
        for title, item in self._values.items():
            del title
            item.setText(placeholder)
            item.setStyleSheet("")


class StepHints(QtWidgets.QWidget):
    """空态里的三步引导：01 输入标的 → 02 调整强度 → 03 阅读结论与依据。

    老版是三个 ACCENT_SOFT 药丸标签，中间用灰色「→」隔开，整体居中。
    """

    def __init__(self, steps: list[str], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(gap(0))
        row.addStretch(1)
        for index, step in enumerate(steps):
            if index:
                row.addWidget(label("→", "hint"))
            row.addWidget(label(step, "step"))
        row.addStretch(1)


def _page_layout(page: QtWidgets.QWidget) -> QtWidgets.QVBoxLayout:
    """给一个功能页装上统一的外边距与卡间距，并让它铺纸面底色。

    五个页面此前各写各的 `QVBoxLayout(self)`（默认边距、默认间距），于是每页的呼吸感都不同。
    私有：五个页面一律经 `scrolling_page` 入口，没有"要边距但不要滚动"的用法。
    """

    page.setProperty("role", "page")
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(gap(2), gap(1), gap(2), gap(1))
    layout.setSpacing(gap(1))
    return layout


def scrolling_page(page: QtWidgets.QWidget) -> QtWidgets.QVBoxLayout:
    """把功能页装进滚动区，返回内容区的布局。

    每页都是若干张卡纵向堆叠，在设计最小窗（tokens.window_minimum_dip = 1000×680）下必然高于
    视口——老 Tkinter 版同样是整页滚动（一个 `tk.Canvas` + 竖向滚动条）。没有滚动区就只能靠
    压扁各张卡来塞进窗口，那正是重构前那版的做法，也正是 `test_qt_visual_matrix` 的裁剪判据
    要拦下的：页面的 minimumSizeHint 必须放得进最小窗。

    横向不滚：内容按宽度自适应，出现横向滚动条即意味着某处宽度失控。
    """

    shell = QtWidgets.QVBoxLayout(page)
    shell.setContentsMargins(0, 0, 0, 0)
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QtWidgets.QWidget()
    layout = _page_layout(content)
    scroll.setWidget(content)
    shell.addWidget(scroll)
    return layout
