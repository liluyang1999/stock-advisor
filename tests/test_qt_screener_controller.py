"""Qt 异步筛选控制器契约（REQ-002/013 / WI-013 / TEST-QT-SC-001 的 Qt 半）。

与 AnalysisController 同构：把 `run_screen` 提交到 QThreadPool，结果经 queued signal 回 GUI 线程，
start() 不阻塞，取消安全。编排/参数解析已由 test_screener_run 覆盖，这里只验证 Qt 线程适配。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt, wait_for
from test_screener import snap

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.screener_controller import ScreenerController


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
class ScreenerControllerTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _controller(self):
        controller = ScreenerController(_FakeScreeningProvider())
        self.addCleanup(controller.shutdown)
        return controller

    def test_start_returns_immediately(self):
        controller = self._controller()
        controller.start("momentum_strong", {}, deep=False)
        self.assertTrue(controller.is_running())

    def test_screen_completes_and_reports_via_signal(self):
        controller = self._controller()
        controller.start("momentum_strong", {"top_n": 10}, deep=False)
        finished = wait_for(controller.screen_finished)
        self.assertTrue(finished, "screen_finished 未在超时内触发")
        report = finished[0][0]
        self.assertTrue(report.ok)
        self.assertLessEqual(len(report.recommendations), 10)
        self.assertFalse(controller.is_running())

    def test_finished_signal_arrives_on_the_gui_thread(self):
        controller = self._controller()
        gui_thread = QtCore.QThread.currentThread()
        delivered_on: list = []
        controller.screen_finished.connect(
            lambda _r: delivered_on.append(QtCore.QThread.currentThread())
        )
        controller.start("momentum_strong", {}, deep=False)
        wait_for(controller.screen_finished)
        self.assertTrue(delivered_on)
        self.assertEqual(delivered_on[0], gui_thread)

    def test_unknown_preset_reports_error_without_crashing(self):
        controller = self._controller()
        controller.start("no_such_preset", {}, deep=False)
        report = wait_for(controller.screen_finished)[0][0]
        self.assertFalse(report.ok)

    def test_cancel_stops_safely(self):
        controller = self._controller()
        controller.start("momentum_strong", {"top_n": 30}, deep=False)
        controller.cancel()
        report = wait_for(controller.screen_finished)[0][0]
        self.assertTrue(report.cancelled or report.ok)  # 取消或已完成，均安全


if __name__ == "__main__":
    unittest.main()
