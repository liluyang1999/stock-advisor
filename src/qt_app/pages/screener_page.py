"""全市场选股页（REQ-002/012/026/031 / WI-013/014/035）。

薄壳：策略预设、可微调参数、结果表、状态行，全部连 `ScreenerController` 的信号。参数解析、排序与
TopN 钳制在 domain，本页不重算。

**版式复刻 WI-023 之前的 Tkinter 版**（WI-035）：

    策略扫描  —— 2×3 策略预设格 + 当前策略说明 + 一行可微调参数 + 开始选股/停止/深度分析
    选股结果  —— 八列结果表（排名 代码 名称 建议 最新价 涨跌幅 筛选分 板块）
    详细解释  —— 选中行的完整判断（深度结论，或只有快照时的快照口径）

重构前这一页是一行下拉框 + 一个数量微调 + 一张无格式的表：六个策略被折进下拉里（选股页的第一个
决定反而最不可见），每个策略各自的可调参数则完全没有入口——预设只能原样跑，不能微调。

而且这一页此前是条**死路**：表格不接选中信号，点中一只候选什么也不会发生，用户拿到的只有"第几名、
多少分"，没有任何"为什么是它"。老版没有这个问题是因为选股结果与个股分析共用同一棵结果树，选中即
出详情（`ui/app_screener.py::_show_selected_detail`）。拆成独立页后那条路径没有跟过来，于是复刻它：
有深度结论就冠上入围抬头给整篇解释，只有快照就给快照口径的详情——两条路径都写一次详情，绝不把
上一只票的解释留在屏幕上冒充当前选中行。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from domain.models import CORE_DISCLAIMER, Recommendation
from domain.presets import PRESETS, TunableParam, get_preset
from services.workflow import ScreenReport
from ui.view_format import build_snapshot_detail
from ui.view_text import build_detail_text, build_recommendation_header, build_screener_overview

from ..controllers.screener_controller import ScreenerController
from ..settings import Settings
from ..widgets.cards import Card, gap, label, scrolling_page
from ..widgets.detail_view import DetailView
from ..widgets.preset_grid import PresetGrid
from ..widgets.table_utils import Column, make_readonly_table, make_row, table_height

_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft
_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight
_CENTRE = QtCore.Qt.AlignmentFlag.AlignHCenter

# 八列，形状沿用老版共用的结果表；选股页额外保留「排名」与「板块」——它们是选股独有的信息，
# 老版把这两项塞进详情文案里，这里既然有独立页面，就正面给出来。
COLUMNS: list[Column] = [
    Column("rank", "排名", 70, _CENTRE),
    Column("code", "代码", 110, _LEFT),
    Column("name", "名称", 150, _LEFT),
    Column("action", "建议", 120, _CENTRE),
    Column("last", "最新价", 100, _RIGHT),
    Column("change", "涨跌幅", 100, _RIGHT),
    Column("score", "筛选分", 90, _RIGHT),
    Column("board", "板块", 120, _LEFT),
]

# 排序口径 → 中文说明，老版在策略说明里一并给出（"（排序：动量优先）"）。
OBJECTIVE_LABELS = {
    "momentum": "动量优先",
    "breakout": "放量突破",
    "activity": "活跃优先",
    "value": "价值优先",
    "rebound": "超跌企稳",
    "balanced": "综合稳健",
}

# 三句引导文案，逐字沿用老 Tkinter 版（`ui/app_screener.py::_finish_screen`）。它们是"接下来该做
# 什么"的唯一出口：零命中要说清放宽哪一类条件、失败要说清失败在哪，否则用户对着一张空表只能猜。
_EMPTY_ADVICE = "没有符合条件的股票，请放宽筛选范围（如降低成交额下限或放宽涨跌幅区间）。"
_FAILURE_ADVICE = "全市场行情暂时取不到，请检查网络后稍后重试。"
_DETAIL_PLACEHOLDER = "点击上方任一候选，这里会展开它的完整解释。"


class ScreenerPage(QtWidgets.QWidget):
    def __init__(
        self,
        controller: ScreenerController,
        settings: Settings,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings
        self._spins: dict[str, QtWidgets.QDoubleSpinBox] = {}
        # 每行对应的候选原件：表格只显示八个格子，详情要的是整只 `Recommendation`（含深度结果、
        # 快照全字段与失败说明）。表不可排序、只追加、整批清空，所以行号与追加顺序始终一一对应。
        self._recommendations: list[Recommendation] = []
        self._build_ui()
        self._connect()
        self._on_preset_changed()

    # ---------------- 构建 ----------------

    def _build_ui(self) -> None:
        layout = scrolling_page(self)

        layout.addWidget(self._build_strategy_card())
        layout.addWidget(self._build_results_card(), 1)
        layout.addWidget(self._build_detail_card(), 1)

        # REQ-031：结果视图常驻免责声明，整页只此一处。
        self.status = label(CORE_DISCLAIMER, "hint", wrap=True)
        layout.addWidget(self.status)
        layout.addStretch(1)

    def _build_strategy_card(self) -> Card:
        card = Card(
            "策略扫描",
            "选择预设并微调参数，从当前全市场快照中筛选；深度分析可继续给出买 / 持 / 卖。",
        )
        # 预设方格。`preset_combo` 这个名字保留下来：接线方与测试都按"下拉框"的接口用它。
        self.preset_combo = PresetGrid()
        restored = self.preset_combo.findData(self._settings.config.preset)
        if restored >= 0:
            self.preset_combo.setCurrentIndex(restored)
        card.body().addWidget(self.preset_combo)

        self.preset_desc = label("", "hint", wrap=True)
        card.body().addWidget(self.preset_desc)

        # 可微调参数：每换一个预设就整行重建（各预设的参数不同）。
        self.tunable_row = QtWidgets.QHBoxLayout()
        self.tunable_row.setSpacing(gap(1))
        card.body().addLayout(self.tunable_row)

        run = QtWidgets.QHBoxLayout()
        run.setSpacing(gap(0))
        self.screen_button = QtWidgets.QPushButton("开始选股")
        self.screen_button.setProperty("role", "primary")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.deep_toggle = QtWidgets.QPushButton("深度分析 开")
        self.deep_toggle.setProperty("role", "switch")
        self.deep_toggle.setCheckable(True)
        self.deep_toggle.setChecked(True)
        run.addWidget(self.screen_button)
        run.addWidget(self.stop_button)
        run.addWidget(self.deep_toggle)
        run.addWidget(label("给买 / 持 / 卖与理由，较慢", "hint"))
        run.addStretch(1)
        card.body().addLayout(run)
        return card

    def _build_results_card(self) -> Card:
        card = Card("选股结果", "按当前策略从全市场快照中排出的候选，排名即入选顺序。")
        self.model, self.table = make_readonly_table(
            COLUMNS,
            "全市场选股结果表",
            empty_hint="选一个策略预设，点「开始选股」，候选按筛选分从高到低列在这里。",
        )
        self.table.setMinimumHeight(table_height(6))
        card.body().addWidget(self.table)

        row = QtWidgets.QHBoxLayout()
        self.overview = label("选股概览：暂无结果。选择策略后点击开始选股。", "overview", wrap=True)
        self.run_status = label("就绪", "hint")
        row.addWidget(self.overview, 1)
        row.addWidget(self.run_status)
        card.body().addLayout(row)
        return card

    def _build_detail_card(self) -> Card:
        """详细解释卡：选中行的完整判断落在这里（老版是结果树下方的同一块详情区）。

        与个股页同一个 `DetailView`：按行着色的规则只有一份（`view_format.detail_line_tags`），
        选股页不另抄一套——同一篇解释在两页里长得不一样，本身就是要避免的事。
        """

        card = Card("详细解释", "点击上方任一行，展开该候选的完整判断与依据。")
        self.detail = DetailView()
        self.detail.setMinimumHeight(240)
        self.detail.clear_detail(_DETAIL_PLACEHOLDER)
        card.body().addWidget(self.detail)
        return card

    def _render_tunables(self) -> None:
        """按当前预设重建参数行：每个参数一列，上标题下微调框（老版的两行网格）。"""

        while self.tunable_row.count():
            item = self.tunable_row.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._spins.clear()

        preset = get_preset(self.preset_combo.currentData()) or PRESETS[0]
        for param in preset.tunables:
            cell = QtWidgets.QWidget()
            column = QtWidgets.QVBoxLayout(cell)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            caption = f"{param.label}（{param.unit}）" if param.unit else param.label
            column.addWidget(label(caption, "hint"))
            column.addWidget(self._make_spin(param, caption))
            self.tunable_row.addWidget(cell, 1)

    def _make_spin(self, param: TunableParam, caption: str) -> QtWidgets.QDoubleSpinBox:
        """一个参数微调框。整数参数（推荐数量）不显示小数位，与老版 `_format_number` 一致。"""

        spin = QtWidgets.QDoubleSpinBox()
        spin.setAccessibleName(caption)
        spin.setRange(float(param.minimum), float(param.maximum))
        integral = float(param.default).is_integer() and float(param.maximum) > 12
        spin.setDecimals(0 if integral else 1)
        spin.setSingleStep(1.0 if integral or float(param.maximum) > 12 else 0.1)
        spin.setValue(float(param.default))
        self._spins[param.key] = spin
        return spin

    def _connect(self) -> None:
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.screen_button.clicked.connect(self._on_screen)
        self.stop_button.clicked.connect(self._controller.cancel)
        self.deep_toggle.toggled.connect(self._on_deep_toggled)
        self._controller.recommendation.connect(self._append_row)
        self._controller.screen_finished.connect(self._on_finished)
        # 这一根线就是本页此前缺的那条路：没有它，结果表点了等于没点。
        selection = self.table.selectionModel()
        if selection is not None:
            selection.currentRowChanged.connect(self._on_row_changed)

    # ---------------- 交互 ----------------

    def _on_deep_toggled(self, checked: bool) -> None:
        self.deep_toggle.setText("深度分析 开" if checked else "深度分析 关")

    def _on_preset_changed(self) -> None:
        """换预设：刷新说明与参数行，并把选择跨会话保留（REQ-009）。"""

        preset = get_preset(self.preset_combo.currentData()) or PRESETS[0]
        objective = OBJECTIVE_LABELS.get(preset.objective, preset.objective)
        self.preset_desc.setText(f"{preset.description}（排序：{objective}）")
        self._render_tunables()
        if not self._settings.update(preset=preset.key):
            self.run_status.setText("设置保存失败（配置文件不可写）")

    def tunable_values(self) -> dict[str, float]:
        """当前参数行的取值。微调框自带范围钳制，所以这里拿到的一定合法。"""

        return {key: spin.value() for key, spin in self._spins.items()}

    # ---------------- 选中行联动 ----------------

    def _on_row_changed(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex) -> None:
        """选中行切换即渲染该候选的详情。

        每条分支都必须写一次详情。留着上一只票的解释比空着更糟：屏幕上那篇文字会被当成当前选中
        行的结论——这正是"看起来还在讲这只票"的误导（REQ-022 的同一条底线）。
        """

        del previous
        rec = self._recommendation_at(current.row()) if current.isValid() else None
        if rec is None:
            self.detail.clear_detail(_DETAIL_PLACEHOLDER)
            return
        if rec.result is not None:
            # 深度结论：整篇解释前冠上"第 N 名 · 板块 · 入选评分"，把"它为什么进这张表"和
            # "它本身怎么样"接起来。抬头必须在前——老版 _show_selected_detail 就是这个顺序，
            # 也只有在前面才当得起 DetailView 的首行大标题。
            self.detail.set_text(
                f"{build_recommendation_header(rec)}\n\n{build_detail_text(rec.result)}"
            )
            return
        # 只有快照（深度分析关着，或这一只深度失败）：给快照口径的详情。失败原因不必在这里另拼，
        # `build_snapshot_detail` 已把 rec.error 同时写进「核心结论」与「需要注意」两节。
        self.detail.set_text(build_snapshot_detail(rec))

    def _recommendation_at(self, row: int) -> Recommendation | None:
        """行号 → 候选。越界返回 None（清表途中到达的迟到选中信号会落在这里）。"""

        if 0 <= row < len(self._recommendations):
            return self._recommendations[row]
        return None

    def _select_first_row(self) -> None:
        """跑完自动选中首行，详情随即出现——不必让用户先猜"这张表是能点的"。"""

        if self.model.rowCount() and not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.model.index(0, 0))

    # ---------------- 运行 ----------------

    def _on_screen(self) -> None:
        # 先清缓存再清表：removeRows 会把选中行顶掉并触发 _on_row_changed，那一刻缓存必须已经
        # 是空的，否则新一轮的第 0 行会短暂显示上一轮第 0 行的解释。
        self._recommendations.clear()
        self.model.removeRows(0, self.model.rowCount())
        self.detail.clear_detail(_DETAIL_PLACEHOLDER)
        self.screen_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        preset = get_preset(self.preset_combo.currentData()) or PRESETS[0]
        self.run_status.setText("筛选中…")
        self.overview.setText(f"选股概览：正在按「{preset.name}」从全市场拉取行情并筛选…")
        # 深度开关此前是个纯装饰：页面从不把它传给控制器，于是无论开关都跑深度分析。
        self._controller.start(preset.key, self.tunable_values(), self.deep_toggle.isChecked())

    def _append_row(self, rec: Recommendation) -> None:
        """一只候选一行。已深度分析的按结论上色；仅快照的按观望色，与老版的行标签一致。"""

        snapshot = rec.snapshot
        if rec.result is not None:
            action_text, action = rec.result.action_label, rec.result.action
        elif rec.error:
            action_text, action = "深度失败", None
        else:
            action_text, action = "快照", "HOLD"
        cells = [
            str(rec.rank),
            snapshot.code,
            snapshot.name,
            action_text,
            f"{snapshot.price:.2f}",
            f"{snapshot.change_pct:+.2f}%",
            f"{rec.screen_score:.1f}",
            rec.board,
        ]
        self.model.appendRow(make_row(cells, COLUMNS, action))
        # 行与候选按同一顺序入列；详情就靠这个下标把八个格子还原成整只 Recommendation。
        self._recommendations.append(rec)

    def _on_finished(self, report: ScreenReport) -> None:
        self.screen_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if not report.ok:
            # 失败要说清失败在哪，而且三处一起说：只改状态行，概览与详情就会永远停在"正在
            # 筛选…"，看起来像还在跑。老版正是在状态、概览、详情三处同时给出原因。
            self.run_status.setText(f"筛选失败：{report.error}")
            self.overview.setText(f"选股概览：{report.error}")
            self.detail.set_text(f"全市场选股失败：{report.error}\n\n{_FAILURE_ADVICE}")
            return
        preset = get_preset(self.preset_combo.currentData()) or PRESETS[0]
        # REQ-026/WI-014：分页不完整时明确提示"非全市场结果"，不把部分结果伪装成全市场。
        partial = (
            "" if report.completeness.is_complete else "（⚠ 全市场分页不完整，以下为部分结果）"
        )
        if report.cancelled:
            self.run_status.setText(f"已停止{partial}")
        elif not report.recommendations:
            # 零命中不是"什么都没发生"：它是一个要用户改条件的结果。老版在这里明确说了放宽哪
            # 一类条件，拆成 Qt 页后这句话丢了，页面只剩一行"推荐 0 只"和一张空表。
            self.run_status.setText(f"没有符合条件的股票{partial}")
            self.overview.setText(
                f"选股概览（{preset.name}）：全市场扫描 {report.total} 只，"
                "没有符合条件的股票，请放宽筛选范围。"
            )
            self.detail.set_text(_EMPTY_ADVICE)
            return
        else:
            self.run_status.setText(
                f"扫描 {report.total} 只，匹配 {report.matched} 只，"
                f"推荐 {len(report.recommendations)} 只{partial}"
            )
        self.overview.setText(
            build_screener_overview(
                preset.name,
                report.total,
                report.matched,
                len(report.recommendations),
                sum(1 for r in report.recommendations if r.error),
            )
        )
        self._select_first_row()
