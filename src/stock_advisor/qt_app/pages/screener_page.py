"""全市场筛选页（REQ-002/012/031 / WI-013）。

薄视图：预设下拉 + TopN 微调 + 筛选/停止按钮 + 结果表 + 状态行，全部连 `ScreenerController` 信号。
页面不含筛选或线程逻辑——用户选预设点"筛选"，控制器在 QThreadPool 上跑，结果经信号回来填进
QTableView。参数解析/排序/TopN 钳制在框架无关的 services 层。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from ...domain.models import CORE_DISCLAIMER
from ...domain.presets import PRESETS
from ...services.workflow import Recommendation, ScreenReport
from ..controllers.screener_controller import ScreenerController
from ..widgets.table_utils import make_readonly_table

_HEADERS = ["排名", "代码", "名称", "最新价", "涨跌幅", "筛选分", "板块"]


class ScreenerPage(QtWidgets.QWidget):
    def __init__(
        self, controller: ScreenerController, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("筛选预设"))
        self.preset_combo = QtWidgets.QComboBox()
        for preset in PRESETS:
            self.preset_combo.addItem(preset.name, preset.key)
        row.addWidget(self.preset_combo)
        row.addWidget(QtWidgets.QLabel("数量"))
        self.top_n = QtWidgets.QSpinBox()
        self.top_n.setRange(5, 30)
        self.top_n.setValue(20)
        row.addWidget(self.top_n)
        self.screen_button = QtWidgets.QPushButton("筛选")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        row.addWidget(self.screen_button)
        row.addWidget(self.stop_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.model, self.table = make_readonly_table(_HEADERS)
        layout.addWidget(self.table)

        # REQ-031：结果视图常驻免责声明。
        self.status = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.screen_button.clicked.connect(self._on_screen)
        self.stop_button.clicked.connect(self._controller.cancel)
        self._controller.recommendation.connect(self._append_row)
        self._controller.screen_finished.connect(self._on_finished)

    def _on_screen(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self.screen_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("筛选中…")
        preset_key = self.preset_combo.currentData()
        self._controller.start(preset_key, {"top_n": self.top_n.value()})

    def _append_row(self, rec: Recommendation) -> None:
        snapshot = rec.snapshot
        cells = [
            str(rec.rank),
            snapshot.code,
            snapshot.name,
            str(snapshot.price),
            f"{snapshot.change_pct:+.2f}%",
            str(rec.screen_score),
            rec.board,
        ]
        self.model.appendRow([QtGui.QStandardItem(text) for text in cells])

    def _on_finished(self, report: ScreenReport) -> None:
        self.screen_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if not report.ok:
            self.status.setText(f"筛选失败：{report.error}　|　{CORE_DISCLAIMER}")
        elif report.cancelled:
            self.status.setText(f"已停止　|　{CORE_DISCLAIMER}")
        else:
            # REQ-026/WI-014：分页不完整时明确提示"非全市场结果"，不把部分结果伪装成全市场。
            partial = (
                "（⚠ 全市场分页不完整，以下为部分结果）"
                if not report.completeness.is_complete
                else ""
            )
            self.status.setText(
                f"扫描 {report.total} 只，匹配 {report.matched} 只，"
                f"推荐 {len(report.recommendations)} 只{partial}　|　{CORE_DISCLAIMER}"
            )
