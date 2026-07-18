"""Qt 异步分析控制器契约（REQ-013 / WI-010 / TEST-QT-AN-001 的 Qt 半）。

编排规则已由 test_batch_controller 覆盖；这里只验证 Qt 适配层：批量分析在 QThreadPool 上跑、
start() 不阻塞调用线程，进度/单只结果/完成经信号回到 GUI 线程，取消能安全停止。信号驱动用
事件循环等待，确定性、不睡眠。
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:  # pragma: no cover - Qt 是可选的迁移期依赖
    QtCore = QtWidgets = None

from stock_advisor.domain.models import Quote

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.analysis_controller import AnalysisController


def _quote(symbol) -> Quote:
    return Quote(
        symbol=symbol.normalized,
        name="测试",
        last=Decimal("10.00"),
        open=Decimal("10.00"),
        high=Decimal("10.50"),
        low=Decimal("9.50"),
        previous_close=Decimal("9.90"),
        volume=1000,
        amount=1.0,
        turnover_rate=0.5,
        change_pct=0.3,
    )


class _FakeProvider:
    def __init__(self, fail_codes=None):
        self.fail_codes = fail_codes or set()

    def fetch_quote(self, symbol):
        if any(code in symbol.normalized for code in self.fail_codes):
            raise ValueError("行情不可用")
        return _quote(symbol)

    def fetch_history(self, symbol):
        return []


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _wait_for(signal, timeout_ms=5000) -> list:
    """阻塞当前(测试)线程的事件循环直到 signal 触发，返回其参数元组列表。不使用 sleep。"""
    loop = QtCore.QEventLoop()
    captured: list = []

    def _catch(*args):
        captured.append(args)
        loop.quit()

    signal.connect(_catch)
    guard = QtCore.QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(loop.quit)
    guard.start(timeout_ms)
    loop.exec()
    return captured


@unittest.skipIf(QtWidgets is None, "PySide6 未安装（pip install --group gui）")
class AnalysisControllerTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()

    def _controller(self, provider):
        controller = AnalysisController(provider)
        self.addCleanup(controller.shutdown)
        return controller

    def test_start_returns_immediately_without_running_to_completion(self):
        # REQ-013：start() 只提交到线程池并立即返回；未跑事件循环时批量尚未完成。
        controller = self._controller(_FakeProvider())
        controller.start("600519 000001")
        self.assertTrue(controller.is_running())  # 已在后台跑，未阻塞调用线程

    def test_batch_completes_and_reports_via_signal(self):
        controller = self._controller(_FakeProvider())
        controller.start("600519 000001")
        finished = _wait_for(controller.batch_finished)
        self.assertTrue(finished, "batch_finished 未在超时内触发")
        report = finished[0][0]
        self.assertEqual(report.total, 2)
        self.assertEqual(report.success_count, 2)
        self.assertFalse(controller.is_running())

    def test_completion_signal_arrives_on_the_gui_thread(self):
        # REQ-013：QWidget 只能在主线程更新，故完成信号必须回到 GUI 线程（queued connection）。
        controller = self._controller(_FakeProvider())
        gui_thread = QtCore.QThread.currentThread()
        delivered_on: list = []
        controller.batch_finished.connect(
            lambda _report: delivered_on.append(QtCore.QThread.currentThread())
        )
        controller.start("600519 000001")
        _wait_for(controller.batch_finished)
        self.assertTrue(delivered_on, "batch_finished 未在超时内触发")
        self.assertEqual(delivered_on[0], gui_thread)

    def test_per_symbol_signals_fire_for_each(self):
        controller = self._controller(_FakeProvider())
        analyzed: list = []
        controller.symbol_analyzed.connect(lambda outcome: analyzed.append(outcome))
        controller.start("600519 000001 600000")
        _wait_for(controller.batch_finished)
        self.assertEqual(len(analyzed), 3)

    def test_single_failure_does_not_abort_the_batch(self):
        controller = self._controller(_FakeProvider(fail_codes={"600519"}))
        controller.start("600519 000001 600000")
        report = _wait_for(controller.batch_finished)[0][0]
        self.assertEqual(report.total, 3)
        self.assertEqual(report.failure_count, 1)
        self.assertEqual(report.success_count, 2)

    def test_input_error_is_reported_without_a_batch(self):
        controller = self._controller(_FakeProvider())
        controller.start("   ")  # 空输入
        report = _wait_for(controller.batch_finished)[0][0]
        self.assertTrue(report.input_error)
        self.assertEqual(report.outcomes, [])

    def test_cancel_stops_the_batch_safely(self):
        controller = self._controller(_FakeProvider())
        controller.start("600519 000001 600000 600036")
        controller.cancel()
        report = _wait_for(controller.batch_finished)[0][0]
        self.assertTrue(report.cancelled)


if __name__ == "__main__":
    unittest.main()
