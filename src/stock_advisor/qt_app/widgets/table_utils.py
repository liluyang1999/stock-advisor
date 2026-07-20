"""表格视图小工具（WI-013 / WI-031）。

`make_readonly_table` 在第三处只读表出现时提取（individual_page、evidence_view、screener_page 都要
"QStandardItemModel 建表头 + QTableView 只读"这套样板）。只封装无争议的构造，不含任何数据逻辑。

**`accessible_name` 是必填的**：表格没有文本，屏幕阅读器只能靠可访问名认出它（REQ-017）。此前它靠
每个调用方自觉去 setAccessibleName，结果 ComparisonView 漏了——而且直到无障碍审计改为遍历装配好的
主窗才暴露出来。把它做成参数，漏不掉。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets


def make_readonly_table(
    headers: list[str],
    accessible_name: str,
) -> tuple[QtGui.QStandardItemModel, QtWidgets.QTableView]:
    """建一个带表头、只读、具名的 QTableView + QStandardItemModel，返回二者供页面填充。"""

    if not accessible_name.strip():
        raise ValueError("只读表必须有可访问名：表格无文本，读屏只能靠它识别（REQ-017）")
    model = QtGui.QStandardItemModel(0, len(headers))
    model.setHorizontalHeaderLabels(headers)
    table = QtWidgets.QTableView()
    table.setModel(model)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAccessibleName(accessible_name)
    return model, table
