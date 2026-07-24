"""表格视图小工具（WI-013 / WI-031 / WI-035）。

`make_readonly_table` 在第三处只读表出现时提取（individual_page、evidence_view、screener_page 都要
"QStandardItemModel 建表头 + QTableView 只读"这套样板）。只封装无争议的构造，不含任何数据逻辑。

**`accessible_name` 是必填的**：表格没有文本，屏幕阅读器只能靠可访问名认出它（REQ-017）。此前它靠
每个调用方自觉去 setAccessibleName，结果 ComparisonView 漏了——而且直到无障碍审计改为遍历装配好的
主窗才暴露出来。把它做成参数，漏不掉。

WI-035 补上老 Tkinter 版表格的三件事，此前 Qt 版一件都没有，于是表格看起来只是一堆等宽白格：
行高按 token（老版 `Treeview` 的 rowheight）、列宽与对齐按列定义、行底色按结论上色（红买绿卖灰观望）。

表头排序（本次）：表头一直是可点的（`sectionsClickable()` 为真），点下去却什么都不发生——
`setSortingEnabled(False)` 恒成立，没有一个调用方传过 `sortable=True`。老版每张表都能点列排序，
这里把它补回来，并且**默认开启**：一个看起来能点的控件不该是空操作。见 `_HeaderSort`。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from domain.formatting import _number_from_cell
from ui.theme import ACTION_ORDER, RISK_ORDER

from ..theme.tokens import load_tokens


@dataclass(frozen=True)
class Column:
    """一列的显示定义：列标识、标题、宽度（逻辑像素）、对齐。

    老版每张 Treeview 都逐列写 `heading(text=...)` + `column(width=, anchor=)`；这里把三者收成
    一个值对象，页面只需要给出列表，宽度/对齐就不会随手漏掉一半。

    `key` 一度只写不读；现在它决定**首次点击该列的排序方向**（见 `_DESCENDING_FIRST`），
    与老版 `_sort_by_column` 按列名判断"首点升序还是降序"是同一份口径。
    """

    key: str
    title: str
    width: int
    align: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignLeft


# 「本格无数据」的占位文案。它们不参与大小比较，升序降序都沉到最后——把 "—" 当 0 排，
# 降序时一排破折号就会压在真实数据前面，正是老版按 `_number_from_cell`（失败返回 0.0）排序的毛病。
_MISSING_CELLS = frozenset({"", "—", "－", "-", "N/A", "未分析", "样本不足", "方向不明"})

# 整格必须"就是一个数"才算数值格：数字 + 可选单位 + 可选括号补充（浮动盈亏的「+3.50%（+1200元）」）。
# 用整格锚定而不是"从文本里抠出第一个数字"，否则名称列的「300ETF」会被当成 300。
_NUMBER = r"[+-]?\d+(?:,\d{3})*(?:\.\d+)?"
_NUMERIC_CELL_RE = re.compile(
    rf"^({_NUMBER})\s*(?:%|分|元|股|手|万|亿|万元|亿元|点|倍)?\s*(?:[（(][^）)]*[）)])?$"
)

# 首点即降序的列（老版 `_sort_by_column` 的同一集合 {score, confidence, change, risk}）：
# 分数/把握/涨跌/风险都是"数值越大越该先看"，首点给升序等于让人再点一次。`conf` 是对比表里
# `confidence` 的别名；中文标题项覆盖以纯字符串表头建表的调用方（那时 key 就等于标题）。
_DESCENDING_FIRST = frozenset(
    {
        "score",
        "confidence",
        "conf",
        "change",
        "risk",
        "综合分",
        "筛选分",
        "把握",
        "置信度",
        "涨跌幅",
        "涨跌",
        "风险",
    }
)


def cell_sort_value(text: str) -> float | str:
    """把一个单元格文本折成可排序值：数值格→float，风险/建议→序号，其余→原文，无数据→空串。

    为什么不直接调 `ui.view_format.table_sort_key`：它的签名是 `(column_key, 整行)`，靠
    `TABLE_COLUMN_INDEX` 去行里取格，而那张索引表只覆盖个股表那 8 列——选股表的 排名/筛选分/板块、
    自选表的 成本/股数/浮动盈亏 都不在其中，套上去只会取错列。所以这里改成**按格判定**：
    只看单元格自己长什么样，五张表共用一套规则，不需要任何按表的列索引。

    数字解析仍复用 `_number_from_cell`（`table_sort_key` 用的就是它），本函数只负责判定"这格是不是
    数值格"并把千分位逗号拿掉——`_number_from_cell` 只 strip `%`/`+`/调用方指定的单位，看到
    `1,234` 会 float 失败并退回 0.0。风险/建议的次序也直接取 `ui.theme` 的 RISK_ORDER / ACTION_ORDER，
    不另立一份。
    """

    stripped = str(text).strip()
    if stripped in _MISSING_CELLS:
        return ""
    # 风险 低/中/高 与建议 买入/持有/卖出 按语义序而非字面序（否则 高<中<低、买入<卖出<继续持有）。
    # 按"格的字面值"匹配即可：这三档与三种结论文案只出现在各自那一列，全表唯一。
    if stripped in RISK_ORDER:
        return RISK_ORDER[stripped]
    if stripped in ACTION_ORDER:
        return ACTION_ORDER[stripped]
    match = _NUMERIC_CELL_RE.match(stripped)
    if match is not None:
        return _number_from_cell(match.group(1).replace(",", ""))
    return stripped


class _HeaderSort(QtCore.QObject):
    """点击表头按该列排序——只重排"看到的行序"，不动模型里的行号。

    为什么不是 `QTableView.setSortingEnabled(True)`：那会让 QStandardItemModel 真的把行搬家，
    而页面普遍拿 `index.row()` 当数据下标（portfolio `_watch_at(row)` 索引 watchlist、alerts 按
    行号删规则、individual 按行号取模型格）。行一搬家，用户选中「A」点删除，掉的就是「B」——
    一个排序功能不该顺手引入一个删错数据的缺陷。改用垂直表头的视觉序（`moveSection`）：模型行号
    原地不动，`index.row()` 仍指向同一条数据，而 QTableView 按视觉序绘制，用户看到的就是排好的表。
    （老版 Tk 用 `tree.move()` 重排、按 iid 取数据，同样不靠行号定位数据。）

    排序键取自单元格的 `Qt.ItemDataRole.UserRole`（`make_row` 建行时就按 `cell_sort_value` 落好），
    没有该角色数据时退回按显示文本现算，所以直接往模型里塞裸 QStandardItem 的调用方也能排。
    """

    def __init__(self, table: QtWidgets.QTableView, columns: list[Column]) -> None:
        super().__init__(table)
        self._table = table
        self._columns = columns
        # 每列各记各的方向（老版 `self.sort_reverse` 字典）：再次点回某列时，从它自己上次的
        # 方向翻转，而不是从头再来一遍首点方向。
        self._orders: dict[int, QtCore.Qt.SortOrder] = {}
        header = table.horizontalHeader()
        if header is not None:
            header.setSectionsClickable(True)
            # 箭头**先不显示**：QHeaderView 默认把指示器画在第 0 列上，未排序时那支箭头会让人
            # 以为表已按「代码」排过。等真正点了某一列再打开（见 `sort_by`）。
            header.setSortIndicatorShown(False)
            header.sectionClicked.connect(self.sort_by)

    def sort_by(self, column: int) -> None:
        if not 0 <= column < len(self._columns):
            return
        order = self._next_order(column)
        self._orders[column] = order
        header = self._table.horizontalHeader()
        if header is not None:
            header.setSortIndicatorShown(True)  # 到这一刻才真的有"按某列排过"
            # QHeaderView 在发出 sectionClicked 之前已自己翻过一次箭头（首点一律升序），
            # 这里覆盖成本列该有的方向，箭头才与实际顺序一致。
            header.setSortIndicator(column, order)
        self._apply(column, order)

    def _next_order(self, column: int) -> QtCore.Qt.SortOrder:
        previous = self._orders.get(column)
        if previous is None:
            spec = self._columns[column]
            first_descending = bool({spec.key, spec.title} & _DESCENDING_FIRST)
            return (
                QtCore.Qt.SortOrder.DescendingOrder
                if first_descending
                else QtCore.Qt.SortOrder.AscendingOrder
            )
        return (
            QtCore.Qt.SortOrder.AscendingOrder
            if previous == QtCore.Qt.SortOrder.DescendingOrder
            else QtCore.Qt.SortOrder.DescendingOrder
        )

    def _apply(self, column: int, order: QtCore.Qt.SortOrder) -> None:
        model = self._table.model()
        rows = self._table.verticalHeader()
        if model is None or rows is None or model.rowCount() < 2:
            return

        numbers: list[tuple[float, int]] = []
        texts: list[tuple[str, int]] = []
        missing: list[int] = []
        for row in range(model.rowCount()):
            value = self._value(model, row, column)
            # 以 str 而非 float 做判别：类型标注里的 `float` 在类型检查器眼中含 int（数值塔提升），
            # `isinstance(value, float)` 为假时剩下的是 `int | str` 而不是 `str`。
            if isinstance(value, str):
                (texts.append((value, row)) if value else missing.append(row))
            else:
                numbers.append((float(value), row))

        reverse = order == QtCore.Qt.SortOrder.DescendingOrder
        # 分三组各自排、再拼接：一列里混着数字与文字（建议列的「买入/加仓」与「深度失败」）时
        # 不会拿 float 去比 str，且无数据的行两个方向都留在最后。同值行保持原有先后（稳定排序）。
        numbers.sort(key=lambda pair: pair[0], reverse=reverse)
        texts.sort(key=lambda pair: pair[0], reverse=reverse)
        ordered = [row for _, row in numbers] + [row for _, row in texts] + missing

        self._table.setUpdatesEnabled(False)
        try:
            for visual, logical in enumerate(ordered):
                rows.moveSection(rows.visualIndex(logical), visual)
        finally:
            self._table.setUpdatesEnabled(True)

    def _value(self, model: QtCore.QAbstractItemModel, row: int, column: int) -> float | str:
        index = model.index(row, column)
        stored = index.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(stored, bool):  # bool 是 int 的子类，别把它当数值排
            return str(stored)
        if isinstance(stored, int | float):
            return float(stored)
        if isinstance(stored, str):
            return stored
        return cell_sort_value(str(index.data(QtCore.Qt.ItemDataRole.DisplayRole) or ""))


# 结论 → （行底色 token, 行字色 token）。红涨绿跌，与光谱条同源。
_ACTION_ROW = {
    "BUY": ("buy_row", "up_red"),
    "SELL": ("sell_row", "down_green"),
    "HOLD": ("hold_row", "muted_ink"),
}


class SelectionFirstDelegate(QtWidgets.QStyledItemDelegate):
    """让"选中"压过按结论上的行底色。

    老版 Treeview 是 `style.map("Treeview", background=[("selected", SELECTION_BG)])`——选中行
    一律翻成浅蓝，盖住 `action_*` 标签的红/绿/灰。Qt 里 `QStandardItem.setBackground()` 写的是
    BackgroundRole，绘制时优先级高于选中高亮，于是选中行看起来跟没选一样。这里在样式选项里把
    背景刷清掉，把绘制权交还给选中高亮。
    """

    def initStyleOption(  # noqa: N802 - Qt 命名
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            option.backgroundBrush = QtGui.QBrush()


def make_readonly_table(
    headers: list[str] | list[Column],
    accessible_name: str,
    empty_hint: str = "",
) -> tuple[QtGui.QStandardItemModel, QtWidgets.QTableView]:
    """建一个带表头、只读、具名、**可点表头排序**的 QTableView + QStandardItemModel。

    `headers` 可以是纯字符串列表（沿用旧调用方），也可以是 `Column` 列表——后者会额外落地列宽、
    对齐与拉伸策略。

    排序默认开启，没有开关参数：表头本来就是可点的，"点了没反应"只会被当成坏了；而原先那个
    `sortable=False` 参数五张表无一传过 True，等于把这条默认路径永久关死。

    `empty_hint` 非空时，空表中央显示一句下一步指引（`_EmptyHint`）：空态是行动邀请，不是一片
    空白——个股页的三步引导是这个原则的特例，其余表此前全是白板。
    """

    if not accessible_name.strip():
        raise ValueError("只读表必须有可访问名：表格无文本，读屏只能靠它识别（REQ-017）")

    columns: list[Column] = [c if isinstance(c, Column) else Column(c, c, 0) for c in headers]
    tokens = load_tokens()

    model = QtGui.QStandardItemModel(0, len(columns))
    model.setHorizontalHeaderLabels([c.title for c in columns])
    # 表头对齐随列：数字列的表头与数值同边，扫读时"列名-列值"才对得上。不落这个角色时
    # QHeaderView 一律居中，代码列表头飘在格值右上方、数字列表头飘在左上方。
    horizontal = QtCore.Qt.Orientation.Horizontal
    for index, column in enumerate(columns):
        model.setHeaderData(
            index,
            horizontal,
            int(column.align | QtCore.Qt.AlignmentFlag.AlignVCenter),
            QtCore.Qt.ItemDataRole.TextAlignmentRole,
        )

    table = QtWidgets.QTableView()
    table.setModel(model)
    table.setItemDelegate(SelectionFirstDelegate(table))
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAccessibleName(accessible_name)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    table.setShowGrid(False)
    table.setWordWrap(False)
    # 刻意保持 Qt 内建排序**关闭**：它会让模型真的搬行，而各页普遍拿 `index.row()` 当数据下标。
    # 排序改由 `_HeaderSort` 重排垂直表头的视觉序完成，模型行号原地不动（详见该类文档）。
    table.setSortingEnabled(False)
    table.setCornerButtonEnabled(False)

    # 行号列不承载信息，只吃宽度——老版 Treeview 用 show="headings" 把它整个去掉了。
    vertical = table.verticalHeader()
    if vertical is not None:
        vertical.setVisible(False)
        vertical.setDefaultSectionSize(tokens.table_row_height_dip)
        vertical.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Fixed)

    header = table.horizontalHeader()
    if header is not None:
        header.setHighlightSections(False)
        header.setMinimumSectionSize(48)
        for index, column in enumerate(columns):
            header.setSectionResizeMode(index, QtWidgets.QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(index, column.width or 100)
        header.setStretchLastSection(False)
        if any(c.width for c in columns):
            # 余宽按各列声明的宽度**按比例**分摊，这正是 Tk Treeview 的默认行为。
            # 换成 Qt 的 Stretch 会把所有列拉成等宽（代码列和名称列一样宽），换成
            # stretchLastSection 又会把余宽全塞给最后一列，两者都不是老版的样子。
            _ProportionalColumns(table, [c.width or 100 for c in columns])

    # 表头点击排序。挂在这里而不是留给调用方——五张表都要，漏挂一张就又是"表头能点却没反应"。
    _HeaderSort(table, columns)

    if empty_hint.strip():
        _EmptyHint(table, model, empty_hint.strip())

    return model, table


class _EmptyHint(QtCore.QObject):
    """空表中央的一句行动指引：有数据让位，清空后回来。

    做成视口里的真实 QLabel 而不是 paintEvent 里的一段画笔文字：真实控件天然参与无障碍树、
    自动继承主题字体，测试也能直接断言可见性，而不用比像素。文案由调用方给出——它必须说
    "下一步做什么"（哪个按钮/哪个输入），而不是抒情的"暂无数据"。
    """

    def __init__(
        self, table: QtWidgets.QTableView, model: QtGui.QStandardItemModel, text: str
    ) -> None:
        viewport = table.viewport()
        super().__init__(viewport)
        self._label = QtWidgets.QLabel(text, viewport)
        self._label.setProperty("role", "empty-hint")
        self._label.setWordWrap(True)
        self._label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        tokens = load_tokens()
        # 指引是提示层级：小一号、灰一档（与 QSS 的 hint 同源取 token，不引第二套颜色）。
        self._label.setStyleSheet(
            f"color: {tokens.colour('muted_ink')};"
            f" font-size: {tokens.font_points['body']}pt;"
            " background: transparent;"
        )
        self._model = model
        self._viewport = viewport
        model.rowsInserted.connect(self._refresh)
        model.rowsRemoved.connect(self._refresh)
        model.modelReset.connect(self._refresh)
        viewport.installEventFilter(self)
        self._refresh()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if event.type() == QtCore.QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(watched, event)

    def _refresh(self, *args: object) -> None:
        del args
        self._label.setVisible(self._model.rowCount() == 0)
        self._reposition()

    def _reposition(self) -> None:
        area = self._viewport.rect()
        margin = load_tokens().spacing_dip[2]
        self._label.setGeometry(area.adjusted(margin, margin, -margin, -margin))


class _ProportionalColumns(QtCore.QObject):
    """让表格在缩放时按声明宽度的比例重新分配列宽。

    挂成事件过滤器而不是重写 QTableView：`make_readonly_table` 返回的是原生 QTableView，
    调用方（含既有测试）不必换成某个子类。
    """

    def __init__(self, table: QtWidgets.QTableView, weights: list[int]) -> None:
        super().__init__(table)
        self._table = table
        self._weights = weights
        self._total = sum(weights) or 1
        table.viewport().installEventFilter(self)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if event.type() == QtCore.QEvent.Type.Resize:
            self._apply()
        return super().eventFilter(watched, event)

    def _apply(self) -> None:
        viewport = self._table.viewport()
        available = viewport.width() if viewport is not None else 0
        if available <= 0:
            return
        used = 0
        for index, weight in enumerate(self._weights[:-1]):
            width = max(48, round(available * weight / self._total))
            self._table.setColumnWidth(index, width)
            used += width
        # 最后一列吃掉舍入误差，避免累计取整后右侧留一条缝。
        self._table.setColumnWidth(len(self._weights) - 1, max(48, available - used))


def table_height(rows: int) -> int:
    """放得下 `rows` 行数据的表格像素高（含表头与边框）。

    五个页面此前各写各的 `row_h * n + 44`——那个 44 是"表头大概这么高"的手算值，控件高度从 44
    调到 32 之后它就全错了，而且错在五个地方。这里按 token 现算：表头与普通控件同高，再留 2px 边框。
    """

    tokens = load_tokens()
    return tokens.table_row_height_dip * rows + tokens.control_min_height_dip + 2


def make_row(
    values: list[str],
    columns: list[Column],
    action: str | None = None,
    tooltip: str | None = None,
) -> list[QtGui.QStandardItem]:
    """按列定义生成一行 item：落地对齐，并按结论上行底色。

    `action` 为 BUY/SELL/HOLD 时整行着色（老版 `result_row_tags` 的 `action_*` 标签）；为 None
    （例如失败行）时不着色——老版失败行也只有"失败"两个字，不额外染色。
    """

    tokens = load_tokens()
    style = _ACTION_ROW.get((action or "").upper())
    background = QtGui.QBrush(QtGui.QColor(tokens.colour(style[0]))) if style else None
    foreground = QtGui.QBrush(QtGui.QColor(tokens.colour(style[1]))) if style else None

    items: list[QtGui.QStandardItem] = []
    for index, value in enumerate(values):
        item = QtGui.QStandardItem(value)
        align = columns[index].align if index < len(columns) else QtCore.Qt.AlignmentFlag.AlignLeft
        item.setTextAlignment(align | QtCore.Qt.AlignmentFlag.AlignVCenter)
        # 排序键随行一起落好：`+9.50%` 要按 9.5 排、`高` 要按风险序排，靠显示文本比大小会得出
        # 「+9.50% < -1.20%」这种字面序。`_HeaderSort` 优先读这个角色，读不到才现算。
        item.setData(cell_sort_value(value), QtCore.Qt.ItemDataRole.UserRole)
        if background is not None:
            item.setBackground(background)
        if foreground is not None:
            item.setForeground(foreground)
        # 整行同一份 tooltip：失败原因这类长文塞不进窄列时，悬停任意一格都能读到全文。
        if tooltip:
            item.setToolTip(tooltip)
        items.append(item)
    return items
