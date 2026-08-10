"""表格视觉精修的行为合同（表头对齐随列、空表有行动邀请）。

两条都源自截图评审时肉眼可见的落差：
1. 表头文字一律居中，而单元格按列定义左/右对齐——数字列的表头飘在格值左上方，扫读时对不上列；
2. 空表是一片白，空态没有任何"下一步做什么"的指引（个股页的三步引导是特例，其余四张表全是空白）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt

if QtWidgets is not None:
    from qt_app.widgets.table_utils import Column, make_readonly_table, table_height

_LEFT = None if QtCore is None else QtCore.Qt.AlignmentFlag.AlignLeft
_RIGHT = None if QtCore is None else QtCore.Qt.AlignmentFlag.AlignRight


@requires_qt
class HeaderAlignmentTests(unittest.TestCase):
    """表头对齐必须与该列单元格的对齐一致，数字列的表头和数值同边。"""

    def setUp(self):
        self.app = qt_app()

    def test_header_alignment_follows_column_alignment(self):
        columns = [
            Column("code", "代码", 120, _LEFT),
            Column("price", "最新价", 100, _RIGHT),
        ]
        model, _table = make_readonly_table(columns, "对齐测试表")

        horizontal = QtCore.Qt.Orientation.Horizontal
        role = QtCore.Qt.ItemDataRole.TextAlignmentRole
        left = model.headerData(0, horizontal, role)
        right = model.headerData(1, horizontal, role)

        self.assertIsNotNone(left, "表头没有落对齐角色：文本列表头应当左对齐")
        self.assertIsNotNone(right, "表头没有落对齐角色：数字列表头应当右对齐")
        self.assertTrue(int(left) & int(_LEFT))
        self.assertTrue(int(right) & int(_RIGHT))


@requires_qt
class EmptyHintTests(unittest.TestCase):
    """空表必须给出下一步指引；一旦有数据，指引让位于数据。"""

    def setUp(self):
        self.app = qt_app()

    def _table(self):
        return make_readonly_table(
            [Column("a", "甲", 100), Column("b", "乙", 100)],
            "空态测试表",
            empty_hint="还没有数据。点上方按钮开始。",
        )

    def _hint_label(self, table):
        labels = [
            w
            for w in table.viewport().findChildren(QtWidgets.QLabel)
            if w.property("role") == "empty-hint"
        ]
        self.assertEqual(len(labels), 1, "空态指引应当恰好一个")
        return labels[0]

    def test_hint_is_visible_on_an_empty_table(self):
        _model, table = self._table()
        hint = self._hint_label(table)
        self.assertEqual(hint.text(), "还没有数据。点上方按钮开始。")
        self.assertTrue(hint.isVisibleTo(table.viewport()))

    def test_hint_disappears_when_rows_arrive_and_returns_when_cleared(self):
        from PySide6 import QtGui

        model, table = self._table()
        hint = self._hint_label(table)

        model.appendRow([QtGui.QStandardItem("x"), QtGui.QStandardItem("y")])
        self.assertFalse(hint.isVisibleTo(table.viewport()), "有数据时指引必须让位")

        model.removeRows(0, model.rowCount())
        self.assertTrue(hint.isVisibleTo(table.viewport()), "清空后指引应当回来")

    def test_tables_without_a_hint_stay_plain(self):
        _model, table = make_readonly_table([Column("a", "甲", 100)], "无指引表")
        labels = [
            w
            for w in table.viewport().findChildren(QtWidgets.QLabel)
            if w.property("role") == "empty-hint"
        ]
        self.assertEqual(labels, [])


@requires_qt
class RowTooltipTests(unittest.TestCase):
    """整行 tooltip：失败原因塞不进窄列时，悬停任意一格都能读到全文。"""

    def setUp(self):
        self.app = qt_app()

    def test_make_row_carries_the_tooltip_on_every_cell(self):
        from qt_app.widgets.table_utils import make_row

        columns = [Column("a", "甲", 100), Column("b", "乙", 100)]
        row = make_row(
            ["x", "很长的失败原因"], columns, tooltip="sz000001 行情不可用：所有源均超时"
        )
        for item in row:
            self.assertEqual(item.toolTip(), "sz000001 行情不可用：所有源均超时")

    def test_rows_without_tooltip_stay_plain(self):
        from qt_app.widgets.table_utils import make_row

        columns = [Column("a", "甲", 100)]
        row = make_row(["x"], columns)
        self.assertEqual(row[0].toolTip(), "")


@requires_qt
class TableHeightTests(unittest.TestCase):
    """表高按 token 现算，而不是各页手抄一个“表头大概这么高”的常数。

    这三条对应 Tk 时代 `gui_layout.GuiLayoutTests` 的三条表高契约（小批量紧凑、空表用较矮的占位
    高度、大批量有界）。此前 tk-contract-mapping 把它们的替代测试记成 `test_qt_result_model`，
    但那个文件测的是一个从未被生产实例化的 `ResultTableModel`，从来没测过表高——契约实际上
    **无人接管**。`table_height` 被五个页面用来定 min/max 高度，这里给它真正的守卫。
    """

    def setUp(self):
        self.app = qt_app()

    def test_height_grows_with_row_count(self):
        heights = [table_height(n) for n in (0, 1, 4, 8, 20)]
        # strict=False 是**有意**的：这是成对滑窗，两个序列本就差一个元素。
        for shorter, taller in zip(heights, heights[1:], strict=False):
            self.assertLess(shorter, taller, "行数变多，表高必须随之变高")

    def test_zero_rows_still_leaves_room_for_the_header(self):
        # 空表不是零高：表头与边框仍要占位，否则空态提示无处可放（老版的“较矮占位高度”）。
        self.assertGreater(table_height(0), 0)

    def test_height_is_linear_so_a_large_batch_stays_bounded(self):
        """每多一行只多一个行高——大批量因此可预测、不会失控（老版“大批量有界”那条）。"""
        step = table_height(2) - table_height(1)
        self.assertGreater(step, 0)
        self.assertEqual(table_height(20) - table_height(10), step * 10)


if __name__ == "__main__":
    unittest.main()
