"""个股批量分析页（REQ-001/003/004/010/013 / WI-010/011/012/027/029/035）。

薄视图：全部业务在 `AnalysisController` 与 domain，本页只负责"谁显示在哪儿"。

**版式复刻 WI-023 之前的 Tkinter 版**（WI-035）。老版这一页自上而下是五张卡：

    墨蓝指挥带（决策强度五档 + 当前档口径）
    研究标的      —— 代码输入框 + 开始分析 / 停止 / 输入工具
    研究结果      —— 概览 / 进度 / 状态，右上角挂复制与导出
      股票列表    —— 八列结果表（代码 名称 建议 综合分 把握 最新价 涨跌幅 风险）
      当前股票摘要 —— 方向/仓位/把握/波动 四格 + 决策强度光谱
      判断依据与价格走势 —— 因子拆解条(36%) │ K 线与成交量(64%)
      详细解释与操作计划 —— 本金 + 章节导航 + 整篇解释

重构前这一页是一个扁平的 QVBoxLayout：输入行、指挥带、表格、splitter(图|证据)、导出行、状态行
六件套直接堆叠，没有卡片、没有分节、没有拉伸配比。结果是表格停在 sizeHint（约三行高）、K 线占掉
整片空白、右栏里的因子表被压成一条缝并与文本框重叠——用户截图里看到的正是这个。

页面本身放在 QScrollArea 里：五张卡在设计最小窗（1000×680）下必然高于视口，老版同样是整页滚动
（一个 `tk.Canvas` + 竖向滚动条）。不给滚动区就只能靠挤压各卡，那正是重构前的做法。

详情区随选中行联动：K 线、因子条、光谱、整篇解释。**决策强度切档只对缓存的 `Measurement` 重判、
不重新联网**（REQ-003）——所以每只票的 `Measurement` 与日线都留在页面里，切档和换行都是本地重算。
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from domain import money
from domain.backtest import backtest_signals
from domain.formatting import risk_level
from domain.models import (
    CORE_DISCLAIMER,
    LEVEL_NAMES,
    AnalysisResult,
    DailyBar,
    Measurement,
)
from domain.policy import flip_hint, position_plan, spectrum
from services import store
from services.batch import BatchProgress, BatchReport
from services.workflow import AnalysisOutcome
from ui.view_format import (
    format_result_row,
    format_results_as_csv,
    format_results_for_clipboard,
    format_table_rows_as_csv,
    format_table_rows_for_clipboard,
)
from ui.view_text import (
    build_backtest_text,
    build_position_plan_text,
    build_visual_summary,
    normalize_symbol_input_text,
    summarize_results,
)

from ..controllers.analysis_controller import AnalysisController
from ..settings import Settings
from ..theme.tokens import load_tokens
from ..widgets.candlestick_chart import CandlestickChart
from ..widgets.cards import (
    Card,
    StatStrip,
    StepHints,
    divider,
    gap,
    label,
    scrolling_page,
)
from ..widgets.detail_view import DetailView
from ..widgets.factor_bars import FactorBars
from ..widgets.spectrum_strip import SpectrumStrip
from ..widgets.table_utils import Column, make_readonly_table, make_row, table_height
from ..widgets.tier_selector import TierSelector

_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft
_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight
_CENTRE = QtCore.Qt.AlignmentFlag.AlignHCenter

# 八列，列名/宽度/对齐逐一沿用老版 Treeview（ui/theme.py 的 TABLE_COLUMNS 就是这一组 key）。
COLUMNS: list[Column] = [
    Column("code", "代码", 110, _LEFT),
    Column("name", "名称", 150, _LEFT),
    Column("action", "建议", 130, _CENTRE),
    Column("score", "综合分", 90, _RIGHT),
    Column("confidence", "把握", 90, _RIGHT),
    Column("last", "最新价", 100, _RIGHT),
    Column("change", "涨跌幅", 100, _RIGHT),
    Column("risk", "风险", 90, _CENTRE),
]

_SUMMARY_CELLS = ["方向", "仓位", "把握", "波动"]
# 详情章节导航，落点是 build_detail_text / build_position_plan_text 里的真实标题。
_DETAIL_NAV = [
    ("结论", "核心结论"),
    ("依据", "判断拆解"),
    ("风险", "需要注意"),
    ("操作", "仓位 / 风控计算器"),
]
# 仓位计算器的默认本金。持久化的本金由 store 管理（REQ-009），此处仅作未配置时的展示基数。
_DEFAULT_CAPITAL = Decimal("100000.00")
_SAMPLE_INPUT = "600519, 000001, 300750, 688981"


class IndividualPage(QtWidgets.QWidget):
    # 跨页请求：本页不认识资金流页，只把"想看这只票的资金流"喊出去，由装配点接线（ADR-0002）。
    fund_flow_requested = QtCore.Signal(str)

    def __init__(
        self,
        controller: AnalysisController,
        settings: Settings,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings
        self._results: list[AnalysisResult] = []
        # 每只票的日线与测量都留在页面里：换行换图、切档重判，两者都不必重新联网
        # （REQ-003 切档不联网 / REQ-004 / WI-027）。
        self._history: dict[str, list[DailyBar]] = {}
        self._measurements: dict[str, Measurement] = {}
        self._failures: dict[str, str] = {}  # normalized -> 失败原因（选中失败行时如实展示）
        # 表格第一列显示的是 `symbol.display`（带交易所前缀，给人看的），而缓存按 `normalized`
        # 建键（给机器用的）。这张表把前者解回后者——少了它，选中一行就查不到自己的日线。
        self._canonical_key: dict[str, str] = {}
        self._build_ui()
        self._connect()

    def _canonical(self, code: str) -> str:
        """把表格里的显示代码解成缓存键；解不出就原样返回（本来就是 normalized 的情形）。"""

        return self._canonical_key.get(code, code)

    # ---------------- 构建 ----------------

    def _build_ui(self) -> None:
        # 外层只放一个滚动区；真正的内容在 `content` 上，与老版"整页滚动"一致。
        layout = scrolling_page(self)

        layout.addWidget(self._build_command_band())
        layout.addWidget(self._build_input_card())
        layout.addWidget(self._build_results_card())
        layout.addWidget(self._build_table_card())
        layout.addWidget(self._build_summary_card())
        layout.addWidget(self._build_workspace_card())
        layout.addWidget(self._build_detail_card())
        layout.addWidget(self._build_placeholder_card())

        # REQ-031：结果视图常驻免责声明。整页只此一处——重构前它同时出现在状态栏、页面状态行、
        # 证据区和仓位区，一屏里重复四遍。
        self.status = label(CORE_DISCLAIMER, "hint", wrap=True)
        layout.addWidget(self.status)
        layout.addStretch(1)

        self._show_results(False)

    def _build_command_band(self) -> QtWidgets.QWidget:
        """墨蓝指挥带：决策强度五档 + 当前档口径。跨会话保留（REQ-009）。"""

        self.tier = TierSelector()
        self.tier.set_level(self._settings.config.level)
        return self.tier

    def _build_input_card(self) -> Card:
        card = Card("研究标的", "最多 30 只，用逗号、空格或换行分隔")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(gap(1))

        # 多行等宽输入：30 个代码在单行框里根本看不全，老版就是一个 3 行的 Consolas Text。
        self.input = QtWidgets.QPlainTextEdit()
        self.input.setProperty("role", "symbols")
        self.input.setPlaceholderText(_SAMPLE_INPUT)
        # REQ-017 可访问名：输入框无文本，屏幕阅读器需显式名（按钮由文本自动取名）。
        self.input.setAccessibleName("股票代码输入")
        self.input.setFixedHeight(84)
        row.addWidget(self.input, 1)
        row.addWidget(divider(QtCore.Qt.Orientation.Vertical))

        # 三个按钮横向并排（老版就是一个 packed RIGHT 的按钮簇），不是竖排——竖排会把输入卡
        # 撑到按钮总高，输入框反而缩在中间一条，上下留出两片空白。
        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(gap(0))
        self.analyze_button = QtWidgets.QPushButton("开始分析")
        self.analyze_button.setProperty("role", "primary")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.tools_button = QtWidgets.QToolButton()
        self.tools_button.setText("输入工具")
        self.tools_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        tools = QtWidgets.QMenu(self.tools_button)
        tools.addAction("整理代码", self.tidy_symbols)
        tools.addAction("示例", lambda: self.input.setPlainText(_SAMPLE_INPUT))
        tools.addAction("清空", self.clear_all)
        self.tools_button.setMenu(tools)
        for button in (self.analyze_button, self.stop_button, self.tools_button):
            buttons.addWidget(button)
        holder = QtWidgets.QWidget()
        holder.setLayout(buttons)
        # 按钮簇与输入框顶端对齐，剩余高度留给输入框而不是摊在按钮上下。
        row.addWidget(holder, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        card.body().addLayout(row)
        card.body().addWidget(
            label(
                "支持沪深代码，可从网页或表格直接粘贴；「整理代码」会去重并补上交易所前缀。", "hint"
            )
        )
        return card

    def _build_results_card(self) -> Card:
        """结果区表头：概览 / 汇总 / 状态 / 进度，右上角挂复制与导出。"""

        card = Card("研究结果", "先浏览股票列表，再查看当前标的的摘要、图表与完整解释。")
        # 老版这一行挂的是「加入自选 / 复制 / 更多」。此前 Qt 版只剩复制与导出：
        # 分析完 8 只想全部加自选，只能切到自选页把 8 个代码再敲一遍；而"完整解释"——这个产品
        # 真正的产出——则根本没有复制入口。
        self.watch_button = QtWidgets.QPushButton("加入自选")
        self.copy_button = QtWidgets.QPushButton("复制结果")
        self.copy_detail_button = QtWidgets.QPushButton("复制解释")
        self.export_button = QtWidgets.QPushButton("导出 CSV")
        for button in (
            self.watch_button,
            self.copy_button,
            self.copy_detail_button,
            self.export_button,
        ):
            button.setEnabled(False)
            card.add_head_widget(button)

        # 老版结果区的「更多」菜单。这里只保留仍需跨页的那一项：资金流页此前要用户把已经选中的
        # 代码再手敲一遍，而老版是直接拿当前选中行的标的去查。
        self.more_button = QtWidgets.QToolButton()
        self.more_button.setText("更多")
        self.more_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        more = QtWidgets.QMenu(self.more_button)
        more.addAction("查看当前标的资金流", self._request_fund_flow)
        self.more_button.setMenu(more)
        card.add_head_widget(self.more_button)

        self.overview = label("组合概览：暂无结果。输入代码后点击开始分析。", "overview", wrap=True)
        card.body().addWidget(self.overview)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(gap(1))
        self.summary = label("暂无结果", "summary")
        self.run_status = label("就绪", "hint")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setAccessibleName("分析进度")
        self.progress.setVisible(False)
        self.progress.setFixedWidth(180)
        row.addWidget(self.summary)
        row.addStretch(1)
        row.addWidget(self.run_status)
        row.addWidget(self.progress)
        card.body().addLayout(row)

        # 预警横幅：规则触发时才出现（老版同样是默认不占位）。
        self.alert_banner = label("", "alert", wrap=True)
        self.alert_banner.setVisible(False)
        card.body().addWidget(self.alert_banner)
        return card

    def _build_table_card(self) -> Card:
        self.table_card = Card("股票列表", "点击任一行，展开该股票的完整判断与依据。")
        self.model, self.table = make_readonly_table(COLUMNS, "个股分析结果表")
        # 至少放得下四行，最多七行后转内部滚动——老版 TABLE_MIN/MAX_VISIBLE_ROWS 的同一意图。
        self.table.setMinimumHeight(table_height(4))
        self.table.setMaximumHeight(table_height(7))
        self.table_card.body().addWidget(self.table)
        return self.table_card

    def _build_summary_card(self) -> Card:
        self.summary_card = Card("当前股票摘要", "方向、建议仓位、把握程度与近期波动")
        self.stats = StatStrip(_SUMMARY_CELLS)
        self.summary_card.body().addWidget(self.stats)
        self.summary_card.body().addWidget(divider())
        # 决策强度光谱：同一只票五档结论一眼对照 + 在哪一档翻转（REQ-003 的对照视图）。
        self.spectrum = SpectrumStrip()
        self.summary_card.body().addWidget(self.spectrum)
        self.flip_hint = label("", "hint", wrap=True)
        self.summary_card.body().addWidget(self.flip_hint)
        return self.summary_card

    def _build_workspace_card(self) -> Card:
        self.workspace_card = Card(
            "判断依据与价格走势", "左侧为因子拆解，右侧为近 90 日 K 线与成交量"
        )
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(0)
        self.factor_bars = FactorBars()
        self.chart = CandlestickChart()
        row.addWidget(self.factor_bars, 36)
        row.addWidget(divider(QtCore.Qt.Orientation.Vertical))
        row.addWidget(self.chart, 64)
        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        holder.setMinimumHeight(300)
        self.workspace_card.body().addWidget(holder)
        return self.workspace_card

    def _build_detail_card(self) -> Card:
        self.detail_card = Card("详细解释与操作计划", "切换章节快速定位；调整本金可即时重算仓位")
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(gap(0))
        bar.addWidget(label("本金", "hint"))
        self.capital_input = QtWidgets.QLineEdit(f"{self._capital():.2f}")
        self.capital_input.setAccessibleName("仓位计算本金输入")
        self.capital_input.setFixedWidth(140)
        bar.addWidget(self.capital_input)
        bar.addWidget(label("即时重算", "hint"))
        bar.addStretch(1)
        bar.addWidget(label("详情", "hint"))

        nav = QtWidgets.QHBoxLayout()
        nav.setSpacing(0)
        self._nav_group = QtWidgets.QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for index, (text, heading) in enumerate(_DETAIL_NAV):
            button = QtWidgets.QPushButton(text)
            button.setProperty("role", "chip")  # 紧凑分段，不吃普通按钮的最小宽度
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setAccessibleName(f"跳到{heading}")
            button.clicked.connect(lambda _=False, h=heading: self.detail.jump_to(h))
            self._nav_group.addButton(button, index)
            nav.addWidget(button)
        bar.addLayout(nav)
        self.detail_card.body().addLayout(bar)

        self.detail = DetailView()
        self.detail.setMinimumHeight(260)
        self.detail_card.body().addWidget(self.detail)
        return self.detail_card

    def _build_placeholder_card(self) -> Card:
        """空态卡：老版在零结果时把表格/摘要/图表/详情整组收起，只留这一张。"""

        self.placeholder = Card()
        column = self.placeholder.body()
        column.setSpacing(gap(1))
        title = label("从一组代码开始", "title")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        lead = label("运行后，这里会按顺序展开结论、图表与可解释依据。", "hint")
        lead.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        column.addWidget(title)
        column.addWidget(lead)
        column.addWidget(StepHints(["01  输入标的", "02  调整强度", "03  阅读结论与依据"]))
        return self.placeholder

    def _show_results(self, visible: bool) -> None:
        """在「空态卡」与「结果四卡」之间切换——两者互斥，绝不同时占位。"""

        for card in (self.table_card, self.summary_card, self.workspace_card, self.detail_card):
            card.setVisible(visible)
        self.placeholder.setVisible(not visible)

    def _connect(self) -> None:
        self.analyze_button.clicked.connect(self._on_analyze)
        self.stop_button.clicked.connect(self._controller.cancel)
        self.copy_button.clicked.connect(self.copy_results)
        self.copy_detail_button.clicked.connect(self.copy_current_detail)
        self.export_button.clicked.connect(self.export_csv)
        self.watch_button.clicked.connect(self.add_all_to_watchlist)
        self._controller.symbol_analyzed.connect(self._append_row)
        self._controller.progress.connect(self._on_progress)
        self._controller.batch_finished.connect(self._on_finished)
        selection = self.table.selectionModel()
        if selection is not None:
            selection.currentRowChanged.connect(self._on_row_changed)
        self.tier.results_changed.connect(self._on_tier_results)
        self.tier.level_changed.connect(self._on_tier_persist)
        self.capital_input.editingFinished.connect(self._on_capital_changed)
        # 本页专属快捷键（老版 Ctrl+L / Ctrl+Shift+C）。作用域限定在本页及其子控件：
        # 「开始分析 / 开始选股」那组是**按当前页派发**的，挂在主窗上（见 app.py 的
        # `_wire_shortcuts`），若这里再挂一份同键，Qt 会判定快捷键歧义而两边都不触发。
        for sequence, handler in (
            ("Ctrl+L", self.clear_all),
            ("Ctrl+Shift+C", self.copy_current_detail),
        ):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

    # ---------------- 输入工具 ----------------

    def symbols_text(self) -> str:
        return self.input.toPlainText()

    def tidy_symbols(self) -> str:
        """去重并补齐交易所前缀（老版「整理代码」）。返回整理后的文本供测试断言。"""

        tidied = normalize_symbol_input_text(self.symbols_text())
        self.input.setPlainText(tidied)
        self.run_status.setText("代码已整理并去重")
        return tidied

    def clear_all(self) -> None:
        """清空输入与结果。**跑到一半按清空要先取消**——否则在途的 worker 会继续把行追加回
        用户刚清掉的表里（老版 `clear()` 同样先 set cancel_event 再清）。"""

        running = not self.analyze_button.isEnabled()
        if running:
            self._controller.cancel()
        self.input.clear()
        self.model.removeRows(0, self.model.rowCount())
        self._results = []
        self._history.clear()
        self._measurements.clear()
        self._failures.clear()
        self._canonical_key.clear()
        self._clear_details()
        self._refresh_action_buttons()
        self._show_results(False)
        self.alert_banner.setVisible(False)
        self.overview.setText("组合概览：暂无结果。输入代码后点击开始分析。")
        self.summary.setText("暂无结果")
        self.run_status.setText("正在停止并清空…" if running else "已清空")

    # ---------------- 选中行联动 ----------------

    def _on_row_changed(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex) -> None:
        """选中行切换时同步 K 线、因子、光谱与解释。失败行没有数据，各视图如实清空。"""

        del previous
        if not current.isValid():
            self._clear_details()
            return
        item = self.model.item(current.row(), 0)
        code = item.text() if item is not None else ""
        name_item = self.model.item(current.row(), 1)
        name = name_item.text() if name_item is not None else ""
        self.chart.set_bars(self._history.get(self._canonical(code), []), f"{code} {name}".strip())
        self._show_details_for(code)

    def _show_details_for(self, code: str) -> None:
        """按当前档位渲染这只票的摘要、因子、光谱与整篇解释。档位变了也走这里，只有一条渲染路径。"""

        result = self._result_for(code)
        if result is None:
            # 只清证据侧，**不动 K 线**：日线来自 outcome.history，判定失败的票照样可能有日线，
            # 而调用方刚刚才把它画上去。这里连图一起清，就等于选中一行后图立刻又消失。
            self._clear_evidence()
            reason = self._failures.get(self._canonical(code))
            if reason:
                # 失败行的"证据"就是失败原因本身——摘要区如实展示全文，不让用户去窄列里猜。
                self.summary_card.set_hint(f"{code} 分析失败：{reason}")
            return

        self.factor_bars.set_factors(list(result.factor_scores))
        self.stats.set_value("方向", result.action_label, self._action_colour(result.action))
        self.stats.set_value("仓位", f"{result.suggested_position:.0%}")
        self.stats.set_value("把握", f"{result.confidence:.0f}%")
        self.stats.set_value("波动", f"{result.expected_move_pct:.1f}%")
        # 一行式摘要沿用老版 build_visual_summary 的措辞（"把握程度"而非"胜率"，REQ-022）。
        self.summary_card.set_hint(build_visual_summary(result))

        measurement = self._measurements.get(self._canonical(code))
        extras: list[str] = []
        if measurement is not None:
            level = self.tier.current_level()
            cells = spectrum(measurement, level)
            self.spectrum.set_cells(cells)
            self.flip_hint.setText(flip_hint(cells))
            extras.append(
                build_position_plan_text(
                    position_plan(measurement, level, self._capital()),
                    LEVEL_NAMES.get(level, str(level)),
                )
            )
        else:
            self.spectrum.clear()
            self.flip_hint.setText("")
        # 可信度回测：同股历史信号事后复盘，逐日只用当日及之前数据（REQ-021 无未来泄漏）。
        # 没有日线也照样交给引擎——它会返回"历史样本不足"的说明。跳过不显示等于让用户对着空白
        # 猜发生了什么，而"说不出结论"本身就是要如实告诉他的结论。
        history = self._history.get(self._canonical(code), [])
        extras.append(
            build_backtest_text(backtest_signals(history, level=self.tier.current_level()))
        )
        self.detail.show_result(result, "\n\n".join(extras))

    def _result_for(self, code: str) -> AnalysisResult | None:
        return next(
            (r for r in self._results if code in (r.symbol.normalized, r.symbol.display)), None
        )

    def _action_colour(self, action: str) -> str:
        tokens = load_tokens()
        return tokens.colour(
            {"BUY": "up_red", "SELL": "down_green"}.get(action.upper(), "muted_ink")
        )

    def _clear_evidence(self) -> None:
        """清空证据侧（因子、光谱、摘要、解释），保留 K 线。"""

        self.factor_bars.clear()
        self.spectrum.clear()
        self.stats.clear()
        self.flip_hint.setText("")
        self.detail.clear_detail()
        self.summary_card.set_hint("方向、建议仓位、把握程度与近期波动")

    def _clear_details(self) -> None:
        """清空整个详情区，含 K 线——换一批分析或取消选中时用。"""

        self.chart.clear()
        self._clear_evidence()

    # ---------------- 档位与本金 ----------------

    def _on_tier_results(self, results: object) -> None:
        """切档：用重判后的结果整体刷新表格与详情。这一步不联网（REQ-003）。"""

        if not isinstance(results, list) or not results:
            return
        self._results = list(results)
        self._refresh_rows()
        self._show_details_for(self._current_code())

    def _current_code(self) -> str:
        index = self.table.currentIndex()
        if not index.isValid():
            return ""
        item = self.model.item(index.row(), 0)
        return item.text() if item is not None else ""

    def _refresh_rows(self) -> None:
        """就地更新已有行，保留选中行——切档不该把用户的选择顶掉。"""

        by_code = {r.symbol.display: r for r in self._results}
        by_code.update({r.symbol.normalized: r for r in self._results})
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            result = by_code.get(item.text()) if item is not None else None
            if result is None:
                continue
            cells = format_result_row(result)
            styled = make_row(list(cells), COLUMNS, result.action)
            for column, source in enumerate(styled):
                target = self.model.item(row, column)
                if target is None:
                    continue
                target.setText(source.text())
                target.setBackground(source.background())
                target.setForeground(source.foreground())

    def _capital(self) -> Decimal:
        """本金：优先用输入框里的当前值，回落到配置，再回落到默认。非法输入不改动已有值。"""

        raw = getattr(self, "capital_input", None)
        if raw is not None:
            parsed = money.positive_money(raw.text())
            if parsed is not None:
                return parsed
        return self._settings.config.capital or _DEFAULT_CAPITAL

    def _on_tier_persist(self) -> None:
        """档位跨会话保留（REQ-009）。存盘失败如实提示，不假装存上了。"""

        if not self._settings.update(level=self.tier.current_level()):
            self.run_status.setText("设置保存失败（配置文件不可写）")

    def _on_capital_changed(self) -> None:
        """本金改了：落盘并按新本金重算当前选中票的仓位。非法输入回填为当前有效值。"""

        capital = money.positive_money(self.capital_input.text())
        if capital is None:
            self.capital_input.setText(f"{self._capital():.2f}")
            return
        self.capital_input.setText(f"{capital:.2f}")
        if not self._settings.update(capital=capital):
            self.run_status.setText("设置保存失败（配置文件不可写）")
        self._show_details_for(self._current_code())

    # ---------------- 运行 ----------------

    def _on_analyze(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self._results = []
        self._history.clear()
        self._measurements.clear()
        self._failures.clear()
        self._canonical_key.clear()
        self._clear_details()
        self._refresh_action_buttons()
        self.analyze_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.alert_banner.setVisible(False)
        self._show_results(True)
        self.summary.setText("分析中")
        self.run_status.setText("分析中…")
        self.overview.setText("组合概览：正在整理行情和判断结果...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._controller.start(self.symbols_text())

    def _on_progress(self, progress: BatchProgress) -> None:
        self.progress.setRange(0, max(1, progress.total))
        self.progress.setValue(progress.done)
        self.run_status.setText(f"已处理 {progress.done}/{progress.total} 只")

    def _append_row(self, outcome: AnalysisOutcome) -> None:
        self._canonical_key[outcome.symbol.display] = outcome.symbol.normalized
        if outcome.history:
            self._history[outcome.symbol.normalized] = list(outcome.history)
        if outcome.measurement is not None:
            self._measurements[outcome.symbol.normalized] = outcome.measurement
        if outcome.ok and outcome.result is not None:
            cells = list(format_result_row(outcome.result))
            action = outcome.result.action
            tooltip = None
        else:
            # 失败行如实标注，并保留数据质量说明；老版同样不给失败行染色。
            reason = outcome.error or outcome.quality.level
            cells = [
                outcome.symbol.display,
                "—",
                "失败",
                "—",
                "—",
                "—",
                "—",
                reason,
            ]
            action = None
            # 原因往往长过"风险"那格：整行 tooltip 给全文，选中行时摘要区也如实显示（见
            # `_show_details_for`）。只截断不给全文，等于让用户猜失败原因。
            tooltip = f"{outcome.symbol.display} 分析失败：{reason}"
            self._failures[outcome.symbol.normalized] = reason
        self.model.appendRow(make_row(cells, COLUMNS, action, tooltip=tooltip))
        self._show_results(True)

    def _on_finished(self, report: BatchReport) -> None:
        self.analyze_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress.setVisible(False)
        # 收集成功结果；动作按钮的开合规则见 `_refresh_action_buttons`
        # （复制/导出看表里有没有行，加入自选与复制解释看有没有成功结果）。
        self._results = [o.result for o in report.outcomes if o.ok and o.result is not None]
        self._refresh_action_buttons()
        # 交给切档器缓存；它随即按当前档位发一次 results_changed，表格与详情由那条路径统一渲染。
        self.tier.set_measurements(
            [o.measurement for o in report.outcomes if o.measurement is not None]
        )
        # 批次结束后自动选中首行，图表随之出现——不必让用户先自己点一下才知道有图。
        if self.model.rowCount() and not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.model.index(0, 0))
        self._show_results(bool(self.model.rowCount()))

        self.summary.setText(summarize_results(self._results, report.failure_count))
        self.overview.setText(self._build_overview(report))
        if report.input_error:
            self.run_status.setText(f"输入有误：{report.input_error}")
        elif report.cancelled:
            self.run_status.setText(f"已停止，已完成 {len(report.outcomes)} 只")
        else:
            self.run_status.setText("分析完成")

    def _build_overview(self, report: BatchReport) -> str:
        """组合概览一行：完成多少、买卖持分布、平均把握、高风险几只、失败几只。"""

        if not self._results:
            return "组合概览：本次没有成功的结果。"
        total = len(self._results)
        buys = sum(1 for r in self._results if r.action == "BUY")
        sells = sum(1 for r in self._results if r.action == "SELL")
        holds = total - buys - sells
        average = sum(r.confidence for r in self._results) / total
        risky = sum(1 for r in self._results if risk_level(r) == "高")
        return (
            f"组合概览：完成 {total} 只，买入 {buys} / 持有 {holds} / 卖出 {sells}；"
            f"平均把握 {average:.0f}%；高风险 {risky} 只；失败 {report.failure_count} 只"
        )

    def _request_fund_flow(self) -> None:
        """把当前选中行的标的交给资金流页去查；没选中就如实提示。"""

        code = self._current_code()
        if not code:
            self.run_status.setText("请先选中一只股票，再查看资金流")
            return
        self.fund_flow_requested.emit(code)

    def show_alert(self, message: str) -> None:
        """预警触发时把横幅显示出来（老版 alert_banner 的同一位置与配色）。"""

        self.alert_banner.setText(message)
        self.alert_banner.setVisible(bool(message))

    def _refresh_action_buttons(self) -> None:
        """按当前状态放开/收起结果区动作；不收参数，避免"传了却被忽略"的陷阱。

        复制/导出看的是**表里有没有行**：全部失败时那张表同样值得导出（用户要的正是那份失败清单）。
        加入自选与复制解释看的是**有没有成功结果**：失败行没有解释可复制，也不该被加进自选。
        """

        has_rows = self.model.rowCount() > 0
        has_results = bool(self._results)
        self.copy_button.setEnabled(has_rows)
        self.export_button.setEnabled(has_rows)
        self.copy_detail_button.setEnabled(has_results)
        self.watch_button.setEnabled(has_results)

    # ---------------- 导出与自选 ----------------

    def _table_rows(self) -> list[tuple[str, ...]]:
        """把表格里**显示着的**每一行读回来（含失败行）。"""

        rows: list[tuple[str, ...]] = []
        for row in range(self.model.rowCount()):
            cells = [self.model.item(row, col) for col in range(self.model.columnCount())]
            rows.append(tuple(cell.text() if cell is not None else "" for cell in cells))
        return rows

    def _has_failures(self) -> bool:
        """表里有行不属于成功结果——失败行只在表里，`self._results` 装不下它们。"""

        return self.model.rowCount() > len(self._results)

    def copy_results(self) -> str:
        """把当前结果按剪贴板格式（含免责声明页脚）拷入系统剪贴板；返回拷贝的文本供测试断言。

        有失败行时导出**表格所见**而不是只导成功的那几只（老版同样按这条规则回退）：
        否则用户分析 10 只、失败 3 只，导出来只有 7 行且没有一个字说明另外 3 只去哪了。
        """

        text = (
            format_table_rows_for_clipboard(self._table_rows())
            if self._has_failures()
            else format_results_for_clipboard(self._results)
        )
        QtWidgets.QApplication.clipboard().setText(text)
        return text

    def copy_current_detail(self) -> str:
        """把当前选中票的**整篇解释**拷进剪贴板（老版「复制」菜单的第二项 / Ctrl+Shift+C）。

        复制结果给的是一张表，适合快速对照；这里给的是"为什么这么判断"的全文，才是这个产品真正
        的产出。返回拷贝的文本供测试断言；没有选中行时返回空串并如实提示，不静默无反应。
        """

        text = self.detail.toPlainText().strip()
        if not text or self._result_for(self._current_code()) is None:
            self.run_status.setText("请先选中一只股票，再复制解释")
            return ""
        QtWidgets.QApplication.clipboard().setText(text)
        self.run_status.setText("已复制当前股票的解释文字")
        return text

    def add_all_to_watchlist(self) -> int:
        """把本次分析出的全部标的一次性加入自选（老版结果区的「加入自选」）。

        老版是一次加完整批，而不是让用户回到自选页逐个重敲代码——分析 8 只就得敲 8 次，
        这正是重构后丢掉这个按钮造成的实际退化。返回新增数量供测试断言。
        """

        if not self._results:
            self.run_status.setText("当前没有可加入自选的分析结果")
            return 0
        existing = {item.code.lower() for item in self._settings.config.watchlist}
        added = [
            store.WatchItem(code=r.symbol.normalized)
            for r in self._results
            if r.symbol.normalized.lower() not in existing
        ]
        if not added:
            self.run_status.setText("本次结果都已在自选中")
            return 0
        merged = [*self._settings.config.watchlist, *added]
        if not self._settings.update(watchlist=merged):
            self.run_status.setText("加入自选失败（配置文件不可写）")
            return 0
        self.run_status.setText(f"已加入自选 {len(added)} 只（自选共 {len(merged)} 只）")
        return len(added)

    def export_csv(self) -> None:
        """弹保存框选路径后写出 CSV。对话框只给路径，写盘在 `export_csv_to`（可离屏测试）。"""

        if not self.model.rowCount():
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出分析结果", "分析结果.csv", "CSV (*.csv)"
        )
        if path:
            self.export_csv_to(Path(path))

    def export_csv_to(self, path: Path) -> None:
        """把当前结果写成 CSV（含 BOM 与免责声明页脚）。文案由 view_format 统一生成。

        与复制同一条回退规则：表里有失败行就导出表格所见，不静默只导成功的那几只。
        """

        text = (
            format_table_rows_as_csv(self._table_rows())
            if self._has_failures()
            else format_results_as_csv(self._results)
        )
        path.write_text(text, encoding="utf-8")
