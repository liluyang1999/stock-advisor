"""自选 / 持仓页（REQ-005/009/012/031 / WI-015/029/035）。

薄视图：一张自选表（可填成本与股数）+ 一次刷新 = 横向对比。**盈亏由 `domain.compare` 算，本页不
自造数字**；没填成本就没有盈亏，表里显示破折号而不是 0——把"没填"显示成"不赚不亏"是伪造。

持久化复用 `services.store`：自选股与持仓成本/股数跨会话保留（REQ-009），改动即存盘，因此用户不必
记得点保存。分析复用 `AnalysisController`——本页持有自己的实例而不是与个股页共用，两页各自的信号
互不串扰，取消也互不影响。

**版式复刻 WI-023 之前的 Tkinter 版**（WI-035）。老版这一块是两个对话框，装进一页后自上而下是两张卡：

    自选股 / 持仓  —— 自选/持仓/已分析/待补 四格指标条 + 五列自选表 + 编辑行（成本/股数/增删改）
    横向对比      —— 对比/买入/高风险/持仓 四格指标条 + 十一列对比表（按结论上色）

重构前这一页是一个扁平的 QVBoxLayout：输入行、三列自选表、按钮行、一个自带第二条免责声明的
`ComparisonView`、状态行五件套直接堆叠。于是老版最有信息量的两样东西都不见了——自选表里没有名称、
没有浮动盈亏（填了成本也看不出赚赔），对比表只有九列且不按买/卖/观望着色。

`ComparisonView` 部件也随之并回本页：老版的横向对比本来就是自选/持仓窗里的一张表，不是另一个
部件；拆成部件后它自带的那条免责声明与页脚那条在同一屏里重复两遍。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from domain import money
from domain.compare import build_comparison_rows
from domain.formatting import risk_level
from domain.input_validate import parse_optional_positive_int
from domain.models import CORE_DISCLAIMER, ComparisonRow
from domain.symbols import normalize_symbol
from services import store
from services.batch import BatchReport
from services.workflow import AnalysisOutcome
from ui.view_format import format_comparison_row, watchlist_rows

from ..controllers.analysis_controller import AnalysisController
from ..settings import Settings
from ..widgets.cards import Card, StatStrip, divider, gap, label, scrolling_page
from ..widgets.table_utils import Column, make_readonly_table, make_row, table_height

_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft
_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight
_CENTRE = QtCore.Qt.AlignmentFlag.AlignHCenter

# 五列，列名/宽度/对齐逐一沿用老版自选/持仓窗的 Treeview（app_watchlist.py 的 watch_headings）。
# 行不着色：自选表列的是"我关注什么"，不是结论，老版同样只给对比表上买/卖/观望色。
WATCH_COLUMNS: list[Column] = [
    Column("code", "代码", 110, _LEFT),
    Column("name", "名称", 130, _LEFT),
    Column("cost", "成本", 90, _RIGHT),
    Column("shares", "股数", 90, _RIGHT),
    Column("pl", "浮动盈亏", 190, _RIGHT),
]

# 十一列，逐列沿用老版横向对比窗的 Treeview（app_watchlist.py 的 headings/anchors），顺序与
# `ui.view_format.format_comparison_row` 的返回顺序严格对应——那个函数就是老版这张表的行格式化器。
COMPARISON_COLUMNS: list[Column] = [
    Column("code", "代码", 100, _LEFT),
    Column("name", "名称", 120, _LEFT),
    Column("last", "现价", 80, _RIGHT),
    Column("change", "涨跌", 80, _RIGHT),
    Column("score", "综合分", 80, _RIGHT),
    Column("conf", "把握", 70, _RIGHT),
    Column("risk", "风险", 60, _CENTRE),
    Column("pos", "建议仓位", 80, _RIGHT),
    Column("cost", "持仓成本", 90, _RIGHT),
    Column("pl", "浮动盈亏", 150, _RIGHT),
    Column("hint", "档位提示", 230, _LEFT),
]

_WATCH_CELLS = ["自选", "持仓", "已分析", "待补"]
_COMPARE_CELLS = ["对比", "买入", "高风险", "持仓"]


class PortfolioPage(QtWidgets.QWidget):
    # 跨页请求：把自选代码交给个股分析页去跑，由装配点接线（ADR-0002）。
    load_into_analysis_requested = QtCore.Signal(str)

    def __init__(
        self,
        controller: AnalysisController,
        settings: Settings,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings
        self._outcomes: dict[str, AnalysisOutcome] = {}
        self._build_ui()
        self._connect()
        self._reload_table()

    # ---------------- 构建 ----------------

    def _build_ui(self) -> None:
        layout = scrolling_page(self)

        layout.addWidget(self._build_watch_card())
        layout.addWidget(self._build_comparison_card())

        # REQ-031：结果视图常驻免责声明，整页只此一处。此前对比部件自带第二条，一屏两遍。
        self.status = label(CORE_DISCLAIMER, "hint", wrap=True)
        layout.addWidget(self.status)
        layout.addStretch(1)

    def _build_watch_card(self) -> Card:
        card = Card(
            "自选股 / 持仓", "维护关注标的；填写成本与股数后，可结合已分析行情查看浮动盈亏。"
        )
        self.watch_stats = StatStrip(_WATCH_CELLS)
        card.body().addWidget(self.watch_stats)
        card.body().addWidget(divider())

        self.model, self.table = make_readonly_table(
            WATCH_COLUMNS,
            "自选持仓表",
            empty_hint="还没有自选。在下方输入代码，点「加入自选」；填上成本与股数即可算浮动盈亏。",
        )
        # 至少放得下四行，超过八行转内部滚动——老版这张 Treeview 是 height=10 的固定高度。
        self.table.setMinimumHeight(table_height(4))
        self.table.setMaximumHeight(table_height(8))
        card.body().addWidget(self.table)

        card.body().addLayout(self._build_edit_row())
        card.body().addWidget(
            label(
                "成本与股数留空表示只关注、未持仓；选中一行会把它的成本与股数填回上面，改完点「保存持仓」。",
                "hint",
                wrap=True,
            )
        )
        return card

    def _build_edit_row(self) -> QtWidgets.QVBoxLayout:
        """输入与操作分行：小窗仍可完整访问所有动作，不靠缩字或横向裁切。"""

        column = QtWidgets.QVBoxLayout()
        column.setSpacing(gap(0))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(gap(0))

        self.code_input = QtWidgets.QLineEdit()
        self.code_input.setPlaceholderText("股票代码")
        # REQ-017 可访问名：输入框无文本，屏幕阅读器需显式名（按钮由文本自动取名）。
        self.code_input.setAccessibleName("自选股代码输入")
        self.code_input.setFixedWidth(110)
        self.cost_input = QtWidgets.QLineEdit()
        self.cost_input.setPlaceholderText("可空")
        self.cost_input.setAccessibleName("持仓成本输入")
        self.cost_input.setFixedWidth(96)
        self.shares_input = QtWidgets.QLineEdit()
        self.shares_input.setPlaceholderText("可空")
        self.shares_input.setAccessibleName("持仓股数输入")
        self.shares_input.setFixedWidth(96)
        for caption, field in (
            ("代码", self.code_input),
            ("成本", self.cost_input),
            ("股数", self.shares_input),
        ):
            row.addWidget(label(caption, "hint"))
            row.addWidget(field)

        row.addStretch(1)
        column.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(gap(0))
        self.add_button = QtWidgets.QPushButton("加入自选")
        self.add_button.setProperty("role", "primary")
        self.save_button = QtWidgets.QPushButton("保存持仓")
        self.remove_button = QtWidgets.QPushButton("移除选中")
        self.refresh_button = QtWidgets.QPushButton("刷新对比")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        # 老版自选窗的「载入到输入框」：把整份自选推回个股分析页并切过去。缺了它，想把自选重新
        # 跑一遍就只能对着自选表把代码逐个抄到分析页。
        self.load_button = QtWidgets.QPushButton("载入分析")
        for button in (
            self.add_button,
            self.save_button,
            self.remove_button,
            self.load_button,
            self.refresh_button,
            self.stop_button,
        ):
            row.addWidget(button)
        row.addStretch(1)
        column.addLayout(row)
        return column

    def _build_comparison_card(self) -> Card:
        card = Card("横向对比", "把已完成深度分析的标的放在同一张表里，比较结论、风险与持仓表现。")
        self.compare_stats = StatStrip(_COMPARE_CELLS)
        card.body().addWidget(self.compare_stats)
        card.body().addWidget(divider())

        self.comparison_model, self.comparison_table = make_readonly_table(
            COMPARISON_COLUMNS,
            "自选持仓横向对比表",
            empty_hint="选中上表的自选，点「载入分析」跑完深度分析后，这里并排比较各标的。",
        )
        self.comparison_table.setMinimumHeight(table_height(5))
        card.body().addWidget(self.comparison_table)
        return card

    def _connect(self) -> None:
        self.add_button.clicked.connect(self.add_current_input)
        self.save_button.clicked.connect(self.save_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.load_button.clicked.connect(self._request_load_into_analysis)
        self.stop_button.clicked.connect(self._controller.cancel)
        self._controller.symbol_analyzed.connect(self._on_symbol)
        self._controller.batch_finished.connect(self._on_finished)
        selection = self.table.selectionModel()
        if selection is not None:
            selection.currentRowChanged.connect(self._on_watch_selected)

    def _request_load_into_analysis(self) -> str:
        """把自选里的代码交给个股分析页。返回交出去的文本供测试断言。

        本页不认识分析页，只发信号，由装配点接线（ADR-0002）。
        """

        codes = [item.code for item in self._config.watchlist]
        if not codes:
            self.status.setText(f"自选是空的，没有可载入的代码　|　{CORE_DISCLAIMER}")
            return ""
        text = ", ".join(codes)
        self.load_into_analysis_requested.emit(text)
        return text

    # --- 自选维护（改动即存盘）---

    def add_current_input(self) -> None:
        code = self.code_input.text().strip()
        if not code:
            return
        normalized = _normalized_code(code)
        if normalized is None:
            self.status.setText(f"代码无效：{code}　|　{CORE_DISCLAIMER}")
            return
        item = store.WatchItem(
            code=normalized,
            cost=money.positive_money(self.cost_input.text()),
            shares=parse_optional_positive_int(self.shares_input.text()),
        )
        # 同一只票再次加入视为更新成本/股数，而不是产生第二行。
        kept = [w for w in self._config.watchlist if w.code.lower() != normalized.lower()]
        self._persist([*kept, item])
        self.code_input.clear()
        self.cost_input.clear()
        self.shares_input.clear()
        self._reload_table()

    def save_selected(self) -> None:
        """把成本 / 股数写回选中的那一行（老版「保存持仓」）。留空表示清除该项，不是写 0。"""

        index = self.table.currentIndex()
        watch = self._watch_at(index.row()) if index.isValid() else None
        if watch is None:
            self.status.setText(f"请先选中一只自选股　|　{CORE_DISCLAIMER}")
            return
        items = list(self._config.watchlist)
        items[index.row()] = store.WatchItem(
            code=watch.code,
            cost=money.positive_money(self.cost_input.text()),
            shares=parse_optional_positive_int(self.shares_input.text()),
        )
        self._persist(items)
        self._reload_table()
        if self._outcomes:
            self._render_comparison()  # 成本变了，浮动盈亏要跟着重算
        else:
            self.status.setText(f"持仓已更新　|　{CORE_DISCLAIMER}")

    def remove_selected(self) -> None:
        index = self.table.currentIndex()
        watch = self._watch_at(index.row()) if index.isValid() else None
        if watch is None:
            return
        self._persist([w for w in self._config.watchlist if w.code != watch.code])
        self._outcomes.pop(watch.code, None)
        self._reload_table()
        self._render_comparison()

    def _watch_at(self, row: int) -> store.WatchItem | None:
        """第 row 行对应的自选项。表格与 watchlist 同序，故按行号索引（老版按 iid 索引，同一做法）。

        不按第一列的文本反查：那一列显示的是 `SH.600000` 这种给人看的形式，而存的是 `sh600000`，
        反查必然对不上。
        """

        items = list(self._config.watchlist)
        return items[row] if 0 <= row < len(items) else None

    @property
    def _config(self) -> store.AppConfig:
        return self._settings.config

    def _persist(self, watchlist: list[store.WatchItem]) -> None:
        """经共享 Settings 做读-改-写：只动 watchlist，不会把别的页刚存的本金/档位覆盖掉。

        存盘失败不该让界面崩，也不该假装成功：update 返回 False 时如实提示。
        """
        if not self._settings.update(watchlist=watchlist):
            self.status.setText(f"自选保存失败（配置文件不可写）　|　{CORE_DISCLAIMER}")

    def _reload_table(self) -> None:
        """按当前自选与已分析结果重画自选表。行文案由 `watchlist_rows` 生成——它就是老版这张表的
        格式化器，名称/浮动盈亏"该股已分析才算"的口径原样沿用。"""

        results = self._results_by_code()
        self.model.removeRows(0, self.model.rowCount())
        for cells in watchlist_rows(list(self._config.watchlist), results):
            self.model.appendRow(make_row(list(cells), WATCH_COLUMNS))
        self._update_watch_stats(results)

    def _results_by_code(self) -> dict:
        """已分析结果按规范化代码索引——`watchlist_rows` 用它给自选行补上名称与浮动盈亏。"""

        return {
            code: outcome.result
            for code, outcome in self._outcomes.items()
            if outcome.ok and outcome.result is not None
        }

    def _update_watch_stats(self, results: dict) -> None:
        """四格指标：自选几只、其中几只填了持仓、几只已分析、还有几只等着补持仓。"""

        watch = list(self._config.watchlist)
        held = sum(1 for w in watch if w.cost is not None or w.shares is not None)
        self.watch_stats.set_value("自选", str(len(watch)))
        self.watch_stats.set_value("持仓", str(held))
        self.watch_stats.set_value("已分析", str(sum(1 for w in watch if w.code in results)))
        self.watch_stats.set_value("待补", str(max(0, len(watch) - held)))

    def _on_watch_selected(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex) -> None:
        """选中一行就把它的成本/股数填回输入框（老版 `<<TreeviewSelect>>` 的同一行为）。

        少了这一步，「保存持仓」就只能凭记忆重填两个数字。
        """

        del previous
        watch = self._watch_at(current.row()) if current.isValid() else None
        if watch is None:
            return
        self.cost_input.setText("" if watch.cost is None else f"{watch.cost:.2f}")
        self.shares_input.setText("" if watch.shares is None else str(watch.shares))

    # --- 刷新对比 ---

    def refresh(self) -> None:
        if not self._config.watchlist:
            self.status.setText(f"自选为空，先加入股票代码　|　{CORE_DISCLAIMER}")
            return
        self._outcomes.clear()
        self.clear_comparison()
        self.refresh_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("刷新中…")
        self._controller.start(" ".join(w.code for w in self._config.watchlist))

    def _on_symbol(self, outcome: AnalysisOutcome) -> None:
        self._outcomes[outcome.symbol.normalized] = outcome

    def _on_finished(self, report: BatchReport) -> None:
        del report
        self.refresh_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        # 自选表也要跟着刷：名称与浮动盈亏这两列本来就"该股已分析才算"。
        self._reload_table()
        self._render_comparison()

    def _render_comparison(self) -> None:
        """把分析结果与自选里的成本/股数配对后交给 domain 组装对比行。

        没有 measurement 的项先过滤掉——`build_comparison_rows` 的契约要求调用方这么做，失败的票
        不该以一行空数据混进对比表。
        """
        by_code = {w.code.lower(): w for w in self._config.watchlist}
        entries = []
        for outcome in self._outcomes.values():
            if not outcome.ok or outcome.result is None or outcome.measurement is None:
                continue
            watch = by_code.get(outcome.symbol.normalized.lower()) or by_code.get(
                outcome.result.symbol.display.lower()
            )
            entries.append(
                {
                    "result": outcome.result,
                    "measurement": outcome.measurement,
                    # 风险列给的是判断风险（低/中/高），与结果表同源——老版这一列就是 risk_level。
                    # 此前这里塞的是数据质量等级（complete/stale/…），于是"风险"列显示 complete，
                    # 而"高风险几只"永远数不出来。数据质量另有 quality 信封承载，不占这一列。
                    "risk": risk_level(outcome.result),
                    "cost": None if watch is None else watch.cost,
                    "shares": None if watch is None else watch.shares,
                }
            )
        self.set_comparison_entries(entries)
        shown = self.comparison_model.rowCount()
        missing = len(self._outcomes) - shown
        note = f"对比 {shown} 只" + (f"，{missing} 只取数失败未纳入" if missing else "")
        self.status.setText(f"{note}　|　{CORE_DISCLAIMER}")

    def set_comparison_entries(self, entries: list[dict]) -> None:
        """接收已深度分析的条目（result/measurement/risk/cost/shares），组装对比行并展示。

        对比排序与浮动盈亏计算是 domain 的事，本页不自造任何数字——无成本时盈亏为空而非 0
        （REQ-005 的语义由引擎给出，展示层如实透出）。行按结论上色（红买绿卖灰观望），与老版
        对比窗的 `action_*` 标签一致。
        """

        rows = build_comparison_rows(entries)
        self.comparison_model.removeRows(0, self.comparison_model.rowCount())
        for row in rows:
            cells = list(format_comparison_row(row))
            self.comparison_model.appendRow(make_row(cells, COMPARISON_COLUMNS, row.action))
        self._update_compare_stats(rows)

    def clear_comparison(self) -> None:
        """清空对比表与它的四格指标。免责声明常驻在页脚，不随表清空。"""

        self.comparison_model.removeRows(0, self.comparison_model.rowCount())
        self._update_compare_stats([])

    def _update_compare_stats(self, rows: list[ComparisonRow]) -> None:
        self.compare_stats.set_value("对比", str(len(rows)))
        self.compare_stats.set_value("买入", str(sum(1 for r in rows if r.action == "BUY")))
        self.compare_stats.set_value("高风险", str(sum(1 for r in rows if r.risk == "高")))
        self.compare_stats.set_value("持仓", str(sum(1 for r in rows if r.cost is not None)))


def _normalized_code(text: str) -> str | None:
    """把用户输入规范化成 `WatchItem` 约定的形式（`sh600519`）；无效返回 None。

    此前这里直接存原样输入，于是内存里是 `600000`、`store` 落盘时又规范成 `sh600000`——同一只票
    在两处对不上，对比表因此永远配不到成本，浮动盈亏一栏恒为破折号。
    """

    try:
        return normalize_symbol(text).normalized
    except ValueError:
        return None


# 股数解析用域里那份（`domain.input_validate.parse_optional_positive_int`），不再在页面里另写。
# 曾经的本地副本 `except (TypeError, ValueError)` 漏了 `OverflowError`，而 `int(float("inf"))`
# 正是抛它——持仓股数填 `inf` 会抛出未捕获异常。域实现先判 `is_integer()` 再转 int，非有限值
# 一律 None（WI-032）。
