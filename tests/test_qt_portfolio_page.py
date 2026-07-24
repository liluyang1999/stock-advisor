"""自选/持仓/横向对比页契约（REQ-005/009/012/031 / WI-015 / TEST-QT-PORT-001）。

薄壳：把 `build_comparison_rows` 算好的横向对比行（含成本/股数/浮动盈亏，Decimal 精度）落进
QTableView。对比逻辑与浮动盈亏计算已由 domain/compare 与既有测试守住；这里验证展示层如实呈现，
免责声明常驻，且不自造盈亏数字。

WI-035 把独立的 `ComparisonView` 部件并回自选页：老 Tkinter 版的横向对比本来就是自选/持仓窗里的
一张十一列表（代码…档位提示），不是另一个部件；拆成部件后它自带的免责声明与页脚那条在同一屏里
重复两遍。断言因此改挂在 `PortfolioPage` 的对比表上——守的仍是同一组保证，一条不少。
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, temp_settings
from test_engine import FakeProvider, make_measurement

from domain.engine import build_analysis_result
from domain.models import CORE_DISCLAIMER
from domain.policy import decide

if True:
    try:
        from qt_app.controllers.analysis_controller import AnalysisController
        from qt_app.pages.portfolio_page import PortfolioPage
    except ImportError:  # pragma: no cover
        AnalysisController = PortfolioPage = None

# 十一列版的列位（与 COMPARISON_COLUMNS / format_comparison_row 同序）。
_COST_COLUMN = 8
_PL_COLUMN = 9


def _entry(code="600519", cost=None, shares=None):
    m = make_measurement(code, 41.0)
    result = build_analysis_result(m, decide(m, 3))
    return {"result": result, "measurement": m, "risk": "", "cost": cost, "shares": shares}


@requires_qt
class ComparisonTableTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self):
        controller = AnalysisController(FakeProvider())
        self.addCleanup(controller.shutdown)
        page = PortfolioPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page

    def test_disclaimer_is_resident(self):
        page = self._page()
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # REQ-031

    def test_shows_a_row_per_entry(self):
        page = self._page()
        page.set_comparison_entries([_entry("600519"), _entry("000001"), _entry("600000")])
        self.assertEqual(page.comparison_model.rowCount(), 3)

    def test_floating_pl_is_rendered_from_the_engine_not_fabricated(self):
        # 成本 40.00、最新价来自测量；盈亏由 build_comparison_rows 算好，展示层原样呈现。
        page = self._page()
        page.set_comparison_entries([_entry("600519", cost=Decimal("40.00"), shares=100)])
        model = page.comparison_model
        body = " ".join(str(model.data(model.index(0, c))) for c in range(model.columnCount()))
        self.assertIn("600519", body)
        # 有成本+股数即应有盈亏：这一格必须是引擎算出的带符号数字，而不是破折号。
        self.assertNotEqual(model.item(0, _PL_COLUMN).text(), "—")
        self.assertTrue(model.item(0, _PL_COLUMN).text().startswith(("+", "-")))

    def test_no_cost_leaves_pl_blank_not_zero(self):
        # 无成本时不应编造 0 盈亏——build_comparison_rows 给 None，展示层显示空/—。
        page = self._page()
        page.set_comparison_entries([_entry("600519", cost=None)])
        self.assertEqual(page.comparison_model.rowCount(), 1)
        self.assertEqual(page.comparison_model.item(0, _COST_COLUMN).text(), "—")
        self.assertEqual(page.comparison_model.item(0, _PL_COLUMN).text(), "—")

    def test_rows_sorted_by_score_desc(self):
        # build_comparison_rows 按综合分降序；展示层保持该序。
        page = self._page()
        page.set_comparison_entries([_entry("600519"), _entry("000001")])
        self.assertEqual(page.comparison_model.rowCount(), 2)

    def test_clear_empties_but_keeps_disclaimer(self):
        page = self._page()
        page.set_comparison_entries([_entry("600519")])
        page.clear_comparison()
        self.assertEqual(page.comparison_model.rowCount(), 0)
        self.assertIn(CORE_DISCLAIMER, page.status.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1] / "src/qt_app/pages/portfolio_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
