"""资金流控制器 + 页契约（REQ-007/031 / WI-017 / TEST-QT-FLOW-001）。

资金流独立、可失败、失败可见降级、不影响核心。控制器异步（QThreadPool），页面薄壳连信号。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, wait_for

from data.data_provider import MarketDataError
from domain.models import CORE_DISCLAIMER, FundFlow

if True:
    try:
        from qt_app.controllers.fund_flow_controller import FundFlowController
        from qt_app.pages.evidence_page import EvidencePage
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

    def test_inflow_values_wear_the_ashare_red(self):
        """净流入是利多：统计带数值与逐日明细都要穿 A 股红（红=流入，绿=流出，色随语义）。"""
        from qt_app.theme.tokens import load_tokens

        up_red = load_tokens().colour("up_red")
        page, controller = self._page(_OkProvider())
        page.input.setText("600519")
        page._on_query()
        wait_for(controller.fund_flow_ready)

        today = page.stats._values["今日主力净额"]
        direction = page.stats._values["今日方向"]
        self.assertIn(up_red.lower(), today.styleSheet().lower(), "净流入数值应着 A 股红")
        self.assertIn(up_red.lower(), direction.styleSheet().lower(), "净流入方向应着 A 股红")

        net_item = page.model.item(0, 1)
        self.assertEqual(net_item.foreground().color().name().lower(), up_red.lower())

    def test_outflow_values_wear_the_ashare_green(self):
        from qt_app.theme.tokens import load_tokens

        class _OutflowProvider:
            def fetch_fund_flow(self, symbol, limit=6):
                return FundFlow(today_main=-2.0e8, main_5d=-5.0e8, recent=[("2026-07-17", -2.0e8)])

        down_green = load_tokens().colour("down_green")
        page, controller = self._page(_OutflowProvider())
        page.input.setText("600519")
        page._on_query()
        wait_for(controller.fund_flow_ready)

        today = page.stats._values["今日主力净额"]
        self.assertIn(down_green.lower(), today.styleSheet().lower(), "净流出数值应着 A 股绿")
        net_item = page.model.item(0, 1)
        self.assertEqual(net_item.foreground().color().name().lower(), down_green.lower())

    def test_success_shows_flow_numbers(self):
        """正文走 `build_fund_flow_text`（与老 Tk 版同源的口径），逐日明细进表。"""
        page, controller = self._page(_OkProvider())
        page.input.setText("600519")
        page._on_query()
        wait_for(controller.fund_flow_ready)
        body = page.body.text()
        self.assertIn("今日主力净额", body)
        self.assertIn("近5日累计", body)
        # 数据源不稳定的提醒必须一并透出，不能只报数字（REQ-007 的可见降级口径）。
        self.assertIn("仅供参考", body)
        self.assertGreater(page.model.rowCount(), 0, "逐日明细表是空的")

    def test_failure_shows_degraded_message_not_crash(self):
        """降级走琥珀警示横幅（role=alert）：警告有警告的样子，而不是一行普通正文。"""
        page, controller = self._page(_FailProvider())
        page.input.setText("600519")
        page._on_query()
        wait_for(controller.fund_flow_ready)
        self.assertTrue(page.warning.isVisibleTo(page), "降级时警示横幅必须可见")
        self.assertIn("资金流暂不可用", page.warning.text())
        self.assertIn("所有源均不可用", page.warning.text())
        self.assertEqual(page.warning.property("role"), "alert")

    def test_success_after_failure_hides_the_warning_banner(self):
        class _FlipProvider:
            def __init__(self):
                self.calls = 0

            def fetch_fund_flow(self, symbol, limit=6):
                self.calls += 1
                if self.calls == 1:
                    raise MarketDataError("所有源均不可用")
                return FundFlow(today_main=1.5e8, main_5d=3.2e8, recent=[("2026-07-17", 1.5e8)])

        page, controller = self._page(_FlipProvider())
        page.input.setText("600519")
        page._on_query()
        wait_for(controller.fund_flow_ready)
        self.assertTrue(page.warning.isVisibleTo(page))
        page._on_query()
        wait_for(controller.fund_flow_ready)
        self.assertFalse(page.warning.isVisibleTo(page), "成功后横幅必须撤下")
        self.assertIn("主力资金流", page.body.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (Path(__file__).resolve().parents[1] / "src/qt_app/pages/evidence_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
