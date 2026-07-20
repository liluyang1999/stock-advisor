"""个股批量分析页（REQ-001/010/013 / WI-010）。

薄视图：输入框 + 分析/停止按钮 + 结果表 + 状态行，全部连 `AnalysisController` 的信号。页面不含
任何分析或线程逻辑——用户点"分析"就 `controller.start(text)`，结果经信号回来后逐行填进表格。
QTableView + QStandardItemModel 承载结果（REQ-012 的模型/视图取向）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...domain.models import CORE_DISCLAIMER, AnalysisResult, DailyBar
from ...services.batch import BatchProgress, BatchReport
from ...services.workflow import AnalysisOutcome
from ...ui.view_format import format_results_as_csv, format_results_for_clipboard
from ..controllers.analysis_controller import AnalysisController
from ..widgets.candlestick_chart import CandlestickChart
from ..widgets.table_utils import make_readonly_table

_HEADERS = ["代码", "名称", "建议", "分数", "最新价", "数据质量"]


class IndividualPage(QtWidgets.QWidget):
    def __init__(
        self, controller: AnalysisController, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._results: list[AnalysisResult] = []
        # 每只票的日线留在页面里：K 线图按选中行切换，重选不必重新联网（REQ-004 / WI-027）。
        self._history: dict[str, list[DailyBar]] = {}
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("输入股票代码，空格或逗号分隔，最多 30 只")
        # REQ-017 可访问名：QLineEdit/表格无文本，屏幕阅读器需显式名（按钮由文本自动取名）。
        self.input.setAccessibleName("股票代码输入")
        self.analyze_button = QtWidgets.QPushButton("分析")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        row.addWidget(self.input)
        row.addWidget(self.analyze_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)

        self.model, self.table = make_readonly_table(_HEADERS)
        self.table.setAccessibleName("个股分析结果表")
        layout.addWidget(self.table)

        self.chart = CandlestickChart()
        layout.addWidget(self.chart)

        # 导出行：复制/CSV 仅在有结果时可用。导出件自带免责声明页脚（见 view_format）。
        export_row = QtWidgets.QHBoxLayout()
        self.copy_button = QtWidgets.QPushButton("复制结果")
        self.export_button = QtWidgets.QPushButton("导出 CSV")
        self.copy_button.setEnabled(False)
        self.export_button.setEnabled(False)
        export_row.addStretch(1)
        export_row.addWidget(self.copy_button)
        export_row.addWidget(self.export_button)
        layout.addLayout(export_row)

        # REQ-031：结果视图常驻免责声明。
        self.status = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.analyze_button.clicked.connect(self._on_analyze)
        self.stop_button.clicked.connect(self._controller.cancel)
        self.input.returnPressed.connect(self._on_analyze)
        self.copy_button.clicked.connect(self.copy_results)
        self.export_button.clicked.connect(self.export_csv)
        self._controller.symbol_analyzed.connect(self._append_row)
        self._controller.progress.connect(self._on_progress)
        self._controller.batch_finished.connect(self._on_finished)
        selection = self.table.selectionModel()
        if selection is not None:
            selection.currentRowChanged.connect(self._on_row_changed)

    def _on_row_changed(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex) -> None:
        """选中行切换时换 K 线。失败行没有日线，图上如实显示"暂无历史数据"，不沿用上一只的图。"""

        del previous
        if not current.isValid():
            self.chart.clear()
            return
        item = self.model.item(current.row(), 0)
        code = item.text() if item is not None else ""
        name_item = self.model.item(current.row(), 1)
        name = name_item.text() if name_item is not None else ""
        self.chart.set_bars(self._history.get(code, []), f"{code} {name}".strip())

    def _on_analyze(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self._results = []
        self._history.clear()
        self.chart.clear()
        self._set_export_enabled(False)
        self.analyze_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("分析中…")
        self._controller.start(self.input.text())

    def _on_progress(self, progress: BatchProgress) -> None:
        self.status.setText(f"分析中… {progress.done}/{progress.total}")

    def _append_row(self, outcome: AnalysisOutcome) -> None:
        if outcome.history:
            self._history[outcome.symbol.normalized] = list(outcome.history)
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
        # 收集成功结果供导出；有结果才放开复制/CSV（失败/取消/空输入则保持禁用）。
        self._results = [o.result for o in report.outcomes if o.ok and o.result is not None]
        self._set_export_enabled(bool(self._results))
        # 批次结束后自动选中首行，K 线随之出现——不必让用户先自己点一下才知道有图。
        if self.model.rowCount() and not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.model.index(0, 0))
        if report.input_error:
            self.status.setText(f"输入有误：{report.input_error}　|　{CORE_DISCLAIMER}")
        elif report.cancelled:
            self.status.setText(f"已停止，已完成 {len(report.outcomes)} 只　|　{CORE_DISCLAIMER}")
        else:
            self.status.setText(
                f"完成：成功 {report.success_count} / 失败 {report.failure_count}"
                f"　|　{CORE_DISCLAIMER}"
            )

    def _set_export_enabled(self, enabled: bool) -> None:
        self.copy_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)

    def copy_results(self) -> str:
        """把当前结果按剪贴板格式（含免责声明页脚）拷入系统剪贴板；返回拷贝的文本供测试断言。"""

        text = format_results_for_clipboard(self._results)
        QtWidgets.QApplication.clipboard().setText(text)
        return text

    def export_csv(self) -> None:
        """弹保存框选路径后写出 CSV。对话框只给路径，写盘在 `export_csv_to`（可离屏测试）。"""

        if not self._results:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出分析结果", "分析结果.csv", "CSV (*.csv)"
        )
        if path:
            self.export_csv_to(Path(path))

    def export_csv_to(self, path: Path) -> None:
        """把当前结果写成 CSV（含 BOM 与免责声明页脚）。文案由 view_format 统一生成。"""

        path.write_text(format_results_as_csv(self._results), encoding="utf-8")
