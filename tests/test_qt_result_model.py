"""个股结果表模型契约（REQ-004/012/031 / WI-011 / TEST-MODEL-001 / TEST-DISC-001）。

REQ-012：QTableView/model 承载结果。REQ-004：展示结论/分数/证据强度/因子/风险/仓位。
REQ-031：免责声明在每个结果视图静态可检测。这里测框架无关能到的部分（模型行/列/角色映射）+
免责声明常量的静态存在。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from PySide6 import QtCore
except ImportError:  # pragma: no cover
    QtCore = None

from qt_test_helpers import requires_qt
from test_engine import make_measurement

from domain.models import CORE_DISCLAIMER
from services.tier_switch import redecide_at_level

if QtCore is not None:
    from qt_app.table_models.result_model import ResultTableModel


def _results(n=3):
    return [redecide_at_level(make_measurement(f"60000{i}", 41.0 + i), 3) for i in range(n)]


@requires_qt
class ResultTableModelTests(unittest.TestCase):
    def test_row_and_column_counts_track_the_results(self):
        model = ResultTableModel()
        self.assertEqual(model.rowCount(), 0)
        model.set_results(_results(3))
        self.assertEqual(model.rowCount(), 3)
        self.assertGreaterEqual(model.columnCount(), 5)

    def test_headers_are_human_labels(self):
        model = ResultTableModel()
        headers = [
            model.headerData(
                c, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.DisplayRole
            )
            for c in range(model.columnCount())
        ]
        self.assertIn("代码", headers)
        self.assertIn("建议", headers)
        self.assertTrue(any("分" in h or "分数" in h for h in headers))

    def test_display_role_returns_the_result_fields(self):
        results = _results(1)
        model = ResultTableModel()
        model.set_results(results)
        row0 = [
            model.data(model.index(0, c), QtCore.Qt.ItemDataRole.DisplayRole)
            for c in range(model.columnCount())
        ]
        self.assertIn(results[0].symbol.code, row0)  # symbol 列显示可读代码
        self.assertIn(results[0].action_label, row0)

    def test_out_of_range_index_returns_none(self):
        model = ResultTableModel()
        model.set_results(_results(1))
        self.assertIsNone(model.data(model.index(5, 0), QtCore.Qt.ItemDataRole.DisplayRole))

    def test_set_results_resets_the_model_cleanly(self):
        model = ResultTableModel()
        model.set_results(_results(3))
        model.set_results(_results(1))  # 换一批
        self.assertEqual(model.rowCount(), 1)

    def test_setting_a_new_tier_reuses_cached_results_without_remeasuring(self):
        # 切档：模型接收重判后的结果，报价列不变（同一测量），只有决策相关列可能变。
        m = make_measurement()
        model = ResultTableModel()
        model.set_results([redecide_at_level(m, 3)])
        last_col = None
        headers = [
            model.headerData(
                c, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.DisplayRole
            )
            for c in range(model.columnCount())
        ]
        if "最新价" in headers:
            last_col = headers.index("最新价")
        price_l3 = model.data(model.index(0, last_col), QtCore.Qt.ItemDataRole.DisplayRole)
        model.set_results([redecide_at_level(m, 5)])
        price_l5 = model.data(model.index(0, last_col), QtCore.Qt.ItemDataRole.DisplayRole)
        self.assertEqual(price_l3, price_l5)  # 报价不因切档而变


class DisclaimerStaticDetectionTests(unittest.TestCase):
    """TEST-DISC-001：免责声明在结果视图源码里静态可检测（不依赖运行 Qt）。"""

    def test_result_model_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1] / "src/qt_app/table_models/result_model.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)

    def test_core_disclaimer_is_the_single_source_string(self):
        self.assertIn("不构成投资建议", CORE_DISCLAIMER)


if __name__ == "__main__":
    unittest.main()
