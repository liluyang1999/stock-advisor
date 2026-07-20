"""筛选页视图契约（REQ-002/012/031 / WI-013 / TEST-QT-SC-001）。

薄壳：6 预设下拉、TopN 微调、结果表、状态行，全部连 ScreenerController 信号。参数解析/排序/
TopN 钳制已由 test_screener_run 覆盖；这里验证页面把信号落进 QTableView、按钮态随生命周期切换、
免责声明常驻。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, temp_settings, wait_for
from test_screener import snap

from stock_advisor.domain.models import CORE_DISCLAIMER
from stock_advisor.domain.presets import PRESETS

if True:  # 延迟 import 让 requires_qt 生效
    try:
        from stock_advisor.qt_app.controllers.screener_controller import ScreenerController
        from stock_advisor.qt_app.pages.screener_page import ScreenerPage
    except ImportError:  # pragma: no cover
        ScreenerController = ScreenerPage = None


class _FakeScreeningProvider:
    def fetch_market_snapshot(self, page_size=1000, max_pages=12):
        return [
            snap(
                code=f"6000{i:02d}",
                price=10.0 + i,
                change_pct=5.0 + i * 0.1,
                volume_ratio=2.0,
                amount=5e8,
            )
            for i in range(30)
        ]

    def fetch_quote(self, symbol):
        raise AssertionError("deep=False 不应触发个股行情")

    def fetch_history(self, symbol):
        return []


@requires_qt
class ScreenerPageTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self):
        controller = ScreenerController(_FakeScreeningProvider())
        self.addCleanup(controller.shutdown)
        page = ScreenerPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page, controller

    def test_offers_all_six_presets(self):
        page, _ = self._page()
        self.assertEqual(page.preset_combo.count(), len(PRESETS))

    def test_disclaimer_is_resident(self):
        page, _ = self._page()
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # REQ-031

    def test_screen_fills_the_result_table(self):
        page, controller = self._page()
        page._on_screen()
        wait_for(controller.screen_finished)
        self.assertGreater(page.model.rowCount(), 0)  # 结果落进 QTableView

    def test_buttons_toggle_across_the_lifecycle(self):
        page, controller = self._page()
        self.assertTrue(page.screen_button.isEnabled())
        self.assertFalse(page.stop_button.isEnabled())
        page._on_screen()
        self.assertFalse(page.screen_button.isEnabled())
        self.assertTrue(page.stop_button.isEnabled())
        wait_for(controller.screen_finished)
        self.assertTrue(page.screen_button.isEnabled())
        self.assertFalse(page.stop_button.isEnabled())

    def test_finished_status_keeps_disclaimer(self):
        page, controller = self._page()
        page._on_screen()
        wait_for(controller.screen_finished)
        self.assertIn(CORE_DISCLAIMER, page.status.text())

    def test_partial_market_is_surfaced_in_status(self):
        # WI-014：分页不完整时页面必须明确提示"非全市场结果"，不静默伪装成全市场。
        from stock_advisor.ports import Completeness

        class _PartialProvider(_FakeScreeningProvider):
            def market_completeness(self):
                return Completeness(expected=100, received=30)

        controller = ScreenerController(_PartialProvider())
        self.addCleanup(controller.shutdown)
        page = ScreenerPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        page._on_screen()
        wait_for(controller.screen_finished)
        self.assertIn("不完整", page.status.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1] / "src/stock_advisor/qt_app/pages/screener_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
