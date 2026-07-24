"""个股资金流页（REQ-007 / REQ-031 / WI-017 / WI-035）。

独立的按需资金流视图：输入代码、查询、展示主力净流入；**失败可见降级**（显示错误说明而非崩溃），
且不进核心分析路径。连 `FundFlowController` 信号，页面不含拉取或线程逻辑。

**版式复刻 WI-023 之前的 Tkinter 版**（WI-035）。老版的资金流是从结果区「更多」菜单弹出的消息框，
正文由 `build_fund_flow_text()` 生成——今日主力净额、近 5 日累计、近几日逐日明细，外加一句数据源
不稳定的提醒。重构前的 Qt 版只有一个输入框、一个按钮和一行 `今日主力净流入 X 元｜近5日 Y 元`：
逐日明细与口径提醒都没有，整页九成是空白。

现在是概览四格（今日净额/方向、近 5 日累计/方向）+ 逐日明细表 + 与老版同源的说明正文。文案仍走
`build_fund_flow_text`，不在 Qt 侧另写一份口径。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from domain.formatting import _flow_direction, _fmt_yi
from domain.models import CORE_DISCLAIMER
from services.fund_flow import FundFlowResult
from ui.view_text import build_fund_flow_text

from ..controllers.fund_flow_controller import FundFlowController
from ..theme.tokens import load_tokens
from ..widgets.cards import Card, StatStrip, gap, label, scrolling_page
from ..widgets.table_utils import Column, make_readonly_table, make_row, table_height

_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft
_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight


def _flow_colour(value: float | None) -> str | None:
    """净额的语义色：正=净流入=A 股红，负=净流出=A 股绿，零/缺失不着色。

    颜色只做冗余通道：数值自带 +/-、方向自带"净流入/净流出"文字（REQ-017 的红绿必配文字），
    这里让统计带与逐日明细跟涨跌幅列同语言，而不是一片墨色。
    """

    if value is None or value == 0:
        return None
    tokens = load_tokens()
    return tokens.colour("up_red") if value > 0 else tokens.colour("down_green")


DAILY_COLUMNS: list[Column] = [
    Column("date", "日期", 140, _LEFT),
    Column("net", "主力净额", 160, _RIGHT),
    Column("direction", "方向", 120, _LEFT),
]

_STAT_CELLS = ["今日主力净额", "今日方向", "近5日累计", "近5日方向"]


class EvidencePage(QtWidgets.QWidget):
    def __init__(
        self, controller: FundFlowController, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        layout = scrolling_page(self)

        query = Card("个股资金流", "按需查询，不进核心分析路径；取不到时如实降级，不影响判断。")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(gap(0))
        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("输入股票代码，例如 600519")
        self.input.setAccessibleName("资金流股票代码输入")  # REQ-017 可访问名
        self.query_button = QtWidgets.QPushButton("查询资金流")
        self.query_button.setProperty("role", "primary")
        row.addWidget(self.input, 1)
        row.addWidget(self.query_button)
        query.body().addLayout(row)
        layout.addWidget(query)

        overview = Card("资金流概览", "净额以「亿」展示，正为净流入、负为净流出。")
        self.stats = StatStrip(_STAT_CELLS)
        overview.body().addWidget(self.stats)
        # 降级警示横幅（琥珀 role=alert）：常驻构造、默认隐藏，失败时亮出、成功时撤下。
        # 警告要有警告的样子——此前降级只是一行普通正文，与说明文案没有视觉区分。
        self.warning = label("", "alert", wrap=True)
        self.warning.setVisible(False)
        overview.body().addWidget(self.warning)
        # 与老版消息框同源的说明正文（含数据源不稳定的提醒）。
        self.body = label("—", wrap=True)
        overview.body().addWidget(self.body)
        layout.addWidget(overview)

        detail = Card("近几日明细", "逐日主力净额，最近 5 个交易日。")
        self.model, self.table = make_readonly_table(
            DAILY_COLUMNS,
            "资金流逐日明细表",
            empty_hint="查询后，这里按日列出最近 5 个交易日的主力净额。",
        )
        self.table.setMinimumHeight(table_height(5))
        detail.body().addWidget(self.table)
        layout.addWidget(detail, 1)

        # REQ-031：结果视图常驻免责声明。
        self.status = label(CORE_DISCLAIMER, "hint", wrap=True)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.query_button.clicked.connect(self._on_query)
        self.input.returnPressed.connect(self._on_query)
        self._controller.fund_flow_ready.connect(self._on_ready)

    def _on_query(self) -> None:
        self.query_button.setEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        self.stats.clear()
        self.warning.setVisible(False)
        self.body.setText("查询中…")
        self._controller.start(self.input.text())

    def _on_ready(self, result: FundFlowResult) -> None:
        self.query_button.setEnabled(True)
        if not result.ok or result.flow is None:
            # REQ-007：可见降级，不崩溃、不影响核心分析。横幅亮出，正文退位。
            # error 由服务层给出且自带「资金流暂不可用：」前缀，这里原样展示、不再拼一层。
            self.warning.setText(result.error or "资金流暂不可用")
            self.warning.setVisible(True)
            self.body.setText("取不到时如实降级；数据源偶发不稳定，可稍后重试。")
            self.stats.clear()
            return
        self.warning.setVisible(False)

        flow = result.flow
        self.body.setText(build_fund_flow_text(flow, self.input.text().strip()))
        self.stats.set_value(
            "今日主力净额", _fmt_yi(flow.today_main), _flow_colour(flow.today_main)
        )
        self.stats.set_value(
            "今日方向", _flow_direction(flow.today_main), _flow_colour(flow.today_main)
        )
        self.stats.set_value("近5日累计", _fmt_yi(flow.main_5d), _flow_colour(flow.main_5d))
        self.stats.set_value("近5日方向", _flow_direction(flow.main_5d), _flow_colour(flow.main_5d))
        for date, value in flow.recent[-5:]:
            row = make_row([date, _fmt_yi(value), _flow_direction(value)], DAILY_COLUMNS)
            colour = _flow_colour(value)
            if colour:
                brush = QtGui.QBrush(QtGui.QColor(colour))
                row[1].setForeground(brush)
                row[2].setForeground(brush)
            self.model.appendRow(row)
