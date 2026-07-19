"""资金流页（REQ-007 / REQ-031 / WI-017）。

独立的按需资金流视图：输入代码、查询、展示主力净流入；**失败可见降级**（显示错误说明而非崩溃），
且不进核心分析路径。连 `FundFlowController` 信号，页面不含拉取或线程逻辑。
"""

from __future__ import annotations

from PySide6 import QtWidgets

from ...domain.models import CORE_DISCLAIMER
from ...services.fund_flow import FundFlowResult
from ..controllers.fund_flow_controller import FundFlowController


class EvidencePage(QtWidgets.QWidget):
    def __init__(
        self, controller: FundFlowController, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("输入股票代码查询主力资金流")
        self.input.setAccessibleName("资金流股票代码输入")  # REQ-017 可访问名
        self.query_button = QtWidgets.QPushButton("查询资金流")
        row.addWidget(self.input)
        row.addWidget(self.query_button)
        layout.addLayout(row)

        self.body = QtWidgets.QLabel("—")
        self.body.setWordWrap(True)
        layout.addWidget(self.body)

        # REQ-031：结果视图常驻免责声明。
        self.status = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.query_button.clicked.connect(self._on_query)
        self.input.returnPressed.connect(self._on_query)
        self._controller.fund_flow_ready.connect(self._on_ready)

    def _on_query(self) -> None:
        self.query_button.setEnabled(False)
        self.body.setText("查询中…")
        self._controller.start(self.input.text())

    def _on_ready(self, result: FundFlowResult) -> None:
        self.query_button.setEnabled(True)
        if not result.ok or result.flow is None:
            # REQ-007：可见降级，不崩溃、不影响核心分析。
            self.body.setText(f"⚠ {result.error}")
            return
        flow = result.flow
        self.body.setText(f"今日主力净流入 {flow.today_main:,.0f} 元｜近5日 {flow.main_5d:,.0f} 元")
