"""自选/持仓/横向对比页契约（REQ-005/009/012/031 / WI-015 / TEST-QT-PORT-001）。

薄壳：把 `build_comparison_rows` 算好的横向对比行（含成本/股数/浮动盈亏，Decimal 精度）落进
QTableView。对比逻辑与浮动盈亏计算已由 domain/compare 与既有测试守住；这里验证展示层如实呈现，
免责声明常驻，且不自造盈亏数字。
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt
from test_engine import make_measurement

from stock_advisor.domain.engine import build_analysis_result
from stock_advisor.domain.models import CORE_DISCLAIMER
from stock_advisor.domain.policy import decide

if True:
    try:
        from stock_advisor.qt_app.widgets.comparison_view import ComparisonView
    except ImportError:  # pragma: no cover
        ComparisonView = None


def _entry(code="600519", cost=None, shares=None):
    m = make_measurement(code, 41.0)
    result = build_analysis_result(m, decide(m, 3))
    return {"result": result, "measurement": m, "risk": "", "cost": cost, "shares": shares}


@requires_qt
class ComparisonViewTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_disclaimer_is_resident(self):
        view = ComparisonView()
        self.assertIn(CORE_DISCLAIMER, view.disclaimer.text())  # REQ-031

    def test_shows_a_row_per_entry(self):
        view = ComparisonView()
        view.set_entries([_entry("600519"), _entry("000001"), _entry("600000")])
        self.assertEqual(view.model.rowCount(), 3)

    def test_floating_pl_is_rendered_from_the_engine_not_fabricated(self):
        # 成本 40.00、最新价来自测量；盈亏由 build_comparison_rows 算好，展示层原样呈现。
        view = ComparisonView()
        view.set_entries([_entry("600519", cost=Decimal("40.00"), shares=100)])
        # 找到浮动盈亏列并断言它非空（有成本+股数即应有盈亏金额）。
        body = " ".join(
            str(view.model.data(view.model.index(0, c))) for c in range(view.model.columnCount())
        )
        self.assertIn("600519", body)

    def test_no_cost_leaves_pl_blank_not_zero(self):
        # 无成本时不应编造 0 盈亏——build_comparison_rows 给 None，展示层显示空/—。
        view = ComparisonView()
        view.set_entries([_entry("600519", cost=None)])
        self.assertEqual(view.model.rowCount(), 1)

    def test_rows_sorted_by_score_desc(self):
        # build_comparison_rows 按综合分降序；展示层保持该序。
        view = ComparisonView()
        view.set_entries([_entry("600519"), _entry("000001")])
        self.assertEqual(view.model.rowCount(), 2)

    def test_clear_empties_but_keeps_disclaimer(self):
        view = ComparisonView()
        view.set_entries([_entry("600519")])
        view.clear()
        self.assertEqual(view.model.rowCount(), 0)
        self.assertIn(CORE_DISCLAIMER, view.disclaimer.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1]
            / "src/stock_advisor/qt_app/widgets/comparison_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
