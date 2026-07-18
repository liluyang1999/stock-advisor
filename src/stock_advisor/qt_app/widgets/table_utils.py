"""表格视图小工具（WI-013）。

`make_readonly_table` 在第三处只读表出现时提取（individual_page、evidence_view、screener_page 都要
"QStandardItemModel 建表头 + QTableView 只读"这套样板）。只封装无争议的构造，不含任何数据逻辑。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets


def make_readonly_table(
    headers: list[str],
) -> tuple[QtGui.QStandardItemModel, QtWidgets.QTableView]:
    """建一个带表头、只读的 QTableView + QStandardItemModel，返回二者供页面填充。"""

    model = QtGui.QStandardItemModel(0, len(headers))
    model.setHorizontalHeaderLabels(headers)
    table = QtWidgets.QTableView()
    table.setModel(model)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    return model, table
