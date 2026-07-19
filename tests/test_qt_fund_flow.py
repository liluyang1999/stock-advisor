"""资金流控制器 + 页契约（REQ-007/031 / WI-017 / TEST-QT-FLOW-001）。

资金流独立、可失败、失败可见降级、不影响核心。控制器异步（QThreadPool），页面薄壳连信号。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, wait_for

from stock_advisor.data.data_provider import MarketDataError
from stock_advisor.domain.models import CORE_DISCLAIMER, FundFlow

if True:
    try:
        from stock_advisor.qt_app.controllers.fund_flow_controller import FundFlowController
        from stock_advisor.qt_app.pages.evidence_page import EvidencePage
    except ImportError:  # pragma: no cover
        FundFlowController = EvidencePage = None


class _OkProvider:
    def fetch_fund_flow(self, symbol, limit=6):
        return FundFlow(today_main=1.5e8, main_5d=3.2e8, recent=[("2026-07-17", 1.5e8)])


class _FailProvider:
    def fetch_fund_flow(self, symbol, limit=6):
        raise MarketDataError("所有源均不可用")


@requires_qt
class FundFlowControllerTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _controller(self, provider):
        controller = FundFlowController(provider)
        self.addCleanup(controller.shutdown)
        return controller

    def test_success_emits_a_flow_result(self):
        controller = self._controller(_OkProvider())
        controller.start("600519")
        got = wait_for(controller.fund_flow_ready)
        self.assertTrue(got)
        self.assertTrue(got[0][0].ok)

    def test_failure_degrades_visibly_not_crash(self):
        controller = self._controller(_FailProvider())
        controller.start("600519")
        got = wait_for(controller.fund_flow_ready)
        self.assertTrue(got)
        self.assertFalse(got[0][0].ok)
        self.assertTrue(got[0][0].error)


@requires_qt
class EvidencePageTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self, provider):
        controller = FundFlowController(provider)
        self.addCleanup(controller.shutdown)
        page = EvidencePage(controller)
        self.addCleanup(page.deleteLater)
        return page, controller

    def test_disclaimer_is_resident(self):
        page, _ = self._page(_OkProvider())
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # REQ-031

    def test_success_shows_flow_numbers(self):
        page, controller = self._page(_OkProvider())
        page.input.setText("600519")
        page._on_query()
        wait_for(controller.fund_flow_ready)
        self.assertIn("主力净流入", page.body.text())

    def test_failure_shows_degraded_message_not_crash(self):
        page, controller = self._page(_FailProvider())
        page.input.setText("600519")
        page._on_query()
        wait_for(controller.fund_flow_ready)
        self.assertIn("⚠", page.body.text())  # 可见降级


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1] / "src/stock_advisor/qt_app/pages/evidence_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
