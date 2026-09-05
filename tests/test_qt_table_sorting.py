"""表头点击排序（WI-035）。

守两件事：

1. **表头点了要真排。** 重构后表头一直是可点的（`sectionsClickable()` 为真），但
   `setSortingEnabled(False)` 恒成立、没有任何调用方传过 `sortable=True`——一个看起来能点的控件
   却是空操作。五张表都受影响。
2. **排序不能按字面值排。** 单元格是 `+9.50%` / `72 分` / `高` 这类带单位的文本，按显示文本比大小
   会得出「+9.50% < -1.20%」「高 < 中 < 低」。数值要按数值排，风险与建议按语义序排。

另外锁一条实现约束：排序**不得搬动模型行号**。各页普遍拿 `index.row()` 当数据下标（自选页按行号
索引 watchlist、预警页按行号删规则），模型一搬家，用户选中 A 点删除掉的就是 B。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtCore, qt_app, requires_qt  # noqa: E402

try:
    from qt_app.widgets.table_utils import (
        Column,
        cell_sort_value,
        make_readonly_table,
        make_row,
    )
except ImportError:  # pragma: no cover - PySide6 是可选的迁移期依赖
    Column = cell_sort_value = make_readonly_table = make_row = None


def _columns():
    return [
        Column("code", "代码", 100),
        Column("change", "涨跌幅", 100),
        Column("risk", "风险", 80),
    ]


@requires_qt
class CellSortValueTests(unittest.TestCase):
    """单格 → 可排序值的口径。"""

    def test_signed_percentages_sort_as_numbers(self):
        self.assertEqual(cell_sort_value("+9.50%"), 9.5)
        self.assertEqual(cell_sort_value("-1.20%"), -1.2)
        self.assertLess(cell_sort_value("-1.20%"), cell_sort_value("+9.50%"))

    def test_units_and_thousands_separators_are_stripped(self):
        self.assertEqual(cell_sort_value("72 分"), 72.0)
        self.assertEqual(cell_sort_value("1,234"), 1234.0)

    def test_risk_uses_semantic_order_not_alphabetical(self):
        low, mid, high = (cell_sort_value(x) for x in ("低", "中", "高"))
        self.assertLess(low, mid)
        self.assertLess(mid, high)

    def test_missing_cells_are_not_treated_as_zero(self):
        """ "—" 当 0 排，降序时一排破折号会压在真实数据前面。"""
        self.assertEqual(cell_sort_value("—"), "")
        self.assertEqual(cell_sort_value(""), "")

    def test_text_that_merely_starts_with_digits_stays_text(self):
        """名称列的「300ETF」不该被当成 300。"""
        self.assertEqual(cell_sort_value("300ETF"), "300ETF")


@requires_qt
class HeaderSortTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()
        self.columns = _columns()
        self.model, self.table = make_readonly_table(self.columns, "排序测试表")
        for code, change, risk in (
            ("A", "+1.00%", "低"),
            ("B", "-5.00%", "高"),
            ("C", "+9.50%", "中"),
        ):
            self.model.appendRow(make_row([code, change, risk], self.columns))

    def _visual_order(self) -> list[str]:
        """按**视觉**顺序读第一列——排序改的是视觉序，不是模型行序。"""
        rows = self.table.verticalHeader()
        return [
            self.model.item(rows.logicalIndex(v), 0).text() for v in range(self.model.rowCount())
        ]

    def _click(self, column: int) -> None:
        self.table.horizontalHeader().sectionClicked.emit(column)

    def test_numeric_column_first_click_is_descending(self):
        """涨跌/分数/把握/风险首点即降序（老版 `_sort_by_column` 的同一集合）。"""
        self._click(1)
        self.assertEqual(self._visual_order(), ["C", "A", "B"])  # +9.50 > +1.00 > -5.00

    def test_clicking_again_reverses(self):
        self._click(1)
        self._click(1)
        self.assertEqual(self._visual_order(), ["B", "A", "C"])

    def test_risk_column_sorts_by_severity(self):
        self._click(2)
        self.assertEqual(self._visual_order(), ["B", "C", "A"])  # 高 > 中 > 低

    def test_text_column_first_click_is_ascending(self):
        self._click(1)  # 先打乱
        self._click(0)
        self.assertEqual(self._visual_order(), ["A", "B", "C"])

    def test_sorting_never_moves_model_rows(self):
        """模型行号必须原地不动——各页拿 index.row() 当数据下标。"""
        before = [self.model.item(r, 0).text() for r in range(self.model.rowCount())]

        self._click(1)
        self._click(2)

        after = [self.model.item(r, 0).text() for r in range(self.model.rowCount())]
        self.assertEqual(before, after, "排序搬动了模型行号，按行号取数据的页面会取错")

    def test_sort_indicator_appears_only_after_a_real_sort(self):
        """未排序时不该有箭头——QHeaderView 默认把它画在第 0 列，会被读成"已按代码排过"。"""
        header = self.table.horizontalHeader()
        self.assertFalse(header.isSortIndicatorShown())

        self._click(1)

        self.assertTrue(header.isSortIndicatorShown())
        self.assertEqual(header.sortIndicatorSection(), 1)

    def test_active_sort_is_reapplied_when_a_value_changes(self):
        self._click(1)
        item = self.model.item(0, 1)
        item.setText("999")
        item.setData(999, QtCore.Qt.ItemDataRole.UserRole)
        self.app.processEvents()
        self.assertEqual(self._visual_order()[0], "A")

    def test_new_rows_join_the_active_sort_without_moving_model_ids(self):
        self._click(1)
        self.model.appendRow(make_row(["D", "999", "低"], self.columns))
        self.app.processEvents()
        self.assertEqual(self._visual_order()[0], "D")
        self.assertEqual(self.model.item(0, 0).text(), "A")


if __name__ == "__main__":
    unittest.main()
