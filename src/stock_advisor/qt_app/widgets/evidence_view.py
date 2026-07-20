"""证据/因子视图（REQ-004 / REQ-022 / REQ-031 / WI-011）。

给定一个 `AnalysisResult`，展示：证据强度（confidence，措辞刻意用"证据强度"而非"胜率/收益概率"
以满足 REQ-022）、8 因子明细（名称/得分/判定/说明，QTableView+model 承载）、以及理由与风险叙述。
免责声明常驻（REQ-031），空态与有数据态都显示。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...domain.models import CORE_DISCLAIMER, AnalysisResult
from .table_utils import make_readonly_table

_FACTOR_HEADERS = ("因子", "得分", "判定", "说明")


class EvidenceView(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        # 证据强度：REQ-022 要求不把未校准分数说成收益概率/胜率，故用"证据强度"这一中性措辞。
        self.strength_label = QtWidgets.QLabel("证据强度：—")
        layout.addWidget(self.strength_label)

        self.factor_model, self.factor_table = make_readonly_table(list(_FACTOR_HEADERS))
        self.factor_table.setAccessibleName("因子明细表")
        layout.addWidget(self.factor_table)

        self.narrative = QtWidgets.QPlainTextEdit()
        self.narrative.setReadOnly(True)
        layout.addWidget(self.narrative)

        # REQ-031：结果视图常驻免责声明，空态即显示。
        self.disclaimer = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.disclaimer)

    def show_result(self, result: AnalysisResult) -> None:
        self.strength_label.setText(f"证据强度：{result.confidence}/100（{result.action_label}）")
        self.factor_model.removeRows(0, self.factor_model.rowCount())
        for factor in result.factor_scores:
            cells = [
                factor.name,
                f"{factor.score:+d}/{factor.max_abs_score}",
                factor.verdict,
                factor.detail,
            ]
            self.factor_model.appendRow([QtGui.QStandardItem(text) for text in cells])

        lines: list[str] = []
        if result.reasons:
            lines.append("主要依据：")
            lines.extend(f"· {reason}" for reason in result.reasons)
        if result.risks:
            lines.append("风险提示：")
            lines.extend(f"· {risk}" for risk in result.risks)
        self.narrative.setPlainText("\n".join(lines))

    def clear(self) -> None:
        self.strength_label.setText("证据强度：—")
        self.factor_model.removeRows(0, self.factor_model.rowCount())
        self.narrative.clear()
        self.disclaimer.setText(CORE_DISCLAIMER)  # 免责声明不因清空而消失

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(480, 360)
