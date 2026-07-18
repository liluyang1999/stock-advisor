"""个股批量分析页（REQ-001/010/013 / WI-010）。

薄视图：输入框 + 分析/停止按钮 + 结果表 + 状态行，全部连 `AnalysisController` 的信号。页面不含
任何分析或线程逻辑——用户点"分析"就 `controller.start(text)`，结果经信号回来后逐行填进表格。
QTableView + QStandardItemModel 承载结果（REQ-012 的模型/视图取向）。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from ...domain.models import CORE_DISCLAIMER
from ...services.batch import BatchProgress, BatchReport
from ...services.workflow import AnalysisOutcome
from ..controllers.analysis_controller import AnalysisController

_HEADERS = ("代码", "名称", "建议", "分数", "最新价", "数据质量")


class IndividualPage(QtWidgets.QWidget):
    def __init__(
        self, controller: AnalysisController, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("输入股票代码，空格或逗号分隔，最多 30 只")
        self.analyze_button = QtWidgets.QPushButton("分析")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        row.addWidget(self.input)
        row.addWidget(self.analyze_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)

        self.model = QtGui.QStandardItemModel(0, len(_HEADERS))
        self.model.setHorizontalHeaderLabels(list(_HEADERS))
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # REQ-031：结果视图常驻免责声明。
        self.status = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.analyze_button.clicked.connect(self._on_analyze)
        self.stop_button.clicked.connect(self._controller.cancel)
        self.input.returnPressed.connect(self._on_analyze)
        self._controller.symbol_analyzed.connect(self._append_row)
        self._controller.progress.connect(self._on_progress)
        self._controller.batch_finished.connect(self._on_finished)

    def _on_analyze(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self.analyze_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("分析中…")
        self._controller.start(self.input.text())

    def _on_progress(self, progress: BatchProgress) -> None:
        self.status.setText(f"分析中… {progress.done}/{progress.total}")

    def _append_row(self, outcome: AnalysisOutcome) -> None:
        if outcome.ok and outcome.result is not None:
            r = outcome.result
            cells = [
                outcome.symbol.normalized,
                r.name,
                r.action_label,
                str(r.score),
                str(r.last),
                outcome.quality.level,
            ]
        else:
            cells = [outcome.symbol.normalized, "—", "失败", "—", "—", outcome.error or "invalid"]
        self.model.appendRow([QtGui.QStandardItem(text) for text in cells])

    def _on_finished(self, report: BatchReport) -> None:
        self.analyze_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if report.input_error:
            self.status.setText(f"输入有误：{report.input_error}　|　{CORE_DISCLAIMER}")
        elif report.cancelled:
            self.status.setText(f"已停止，已完成 {len(report.outcomes)} 只　|　{CORE_DISCLAIMER}")
        else:
            self.status.setText(
                f"完成：成功 {report.success_count} / 失败 {report.failure_count}"
                f"　|　{CORE_DISCLAIMER}"
            )
