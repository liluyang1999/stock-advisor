"""自选/持仓横向对比视图（REQ-005 / REQ-012 / REQ-031 / WI-015）。

纯展示：把 `domain.compare.build_comparison_rows` 算好的 `ComparisonRow`（含成本、浮动盈亏，
金额为 Decimal 2 位）落进 QTableView。对比排序与浮动盈亏计算是 domain 的事，本视图不自造任何
数字——无成本时盈亏为空而非 0（REQ-005 的语义由引擎给出，展示层如实透出）。免责声明常驻。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from ...domain.compare import build_comparison_rows
from ...domain.models import CORE_DISCLAIMER, ComparisonRow
from .table_utils import make_readonly_table

_HEADERS = ["代码", "名称", "最新价", "涨跌幅", "综合分", "建议", "成本", "浮动盈亏", "盈亏额"]


class ComparisonView(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.model, self.table = make_readonly_table(_HEADERS)
        layout.addWidget(self.table)
        # REQ-031：结果视图常驻免责声明。
        self.disclaimer = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.disclaimer)

    def set_entries(self, entries: list[dict]) -> None:
        """接收已深度分析的条目（result/measurement/risk/cost/shares），组装对比行并展示。"""
        self.model.removeRows(0, self.model.rowCount())
        for row in build_comparison_rows(entries):
            self._append_row(row)

    def _append_row(self, row: ComparisonRow) -> None:
        cells = [
            row.code,
            row.name,
            _fmt(row.last),
            f"{row.change_pct:+.2f}%" if row.change_pct is not None else "—",
            str(row.score),
            row.action,
            _fmt(row.cost),
            f"{row.pl_pct:+.2f}%" if row.pl_pct is not None else "—",
            _fmt(row.pl_amount),
        ]
        self.model.appendRow([QtGui.QStandardItem(text) for text in cells])

    def clear(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self.disclaimer.setText(CORE_DISCLAIMER)


def _fmt(value: object) -> str:
    """金额/报价（Decimal）与缺失值的统一展示：None -> '—'，否则原样字符串。"""
    return "—" if value is None else str(value)
