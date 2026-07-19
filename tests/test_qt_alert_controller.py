"""Qt 预警监控控制器契约（REQ-006/010/013 / WI-016 / TEST-QT-ALERT-001 / RISK-005）。

QTimer 周期性把一轮监控提交到 QThreadPool，新触发经 queued signal 回 GUI 线程；**generation 计数
丢弃迟到结果**（停止监控或重启后，上一代 worker 的迟到结果不得覆盖新状态——RISK-005）。
一条规则/一只失败不停监控（REQ-010），GUI 不阻塞（REQ-013）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt, wait_for
from test_engine import FakeProvider

from stock_advisor.domain.models import AlertRule

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.alert_controller import AlertController


def _rule(code, threshold=5.0):
    return AlertRule(code=code, field="price", op=">=", threshold=threshold, enabled=True)


@requires_qt
class AlertControllerTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _controller(self, provider=None):
        controller = AlertController(provider or FakeProvider())
        self.addCleanup(controller.shutdown)
        return controller

    def test_not_running_until_started(self):
        controller = self._controller()
        self.assertFalse(controller.is_running())

    def test_start_runs_a_cycle_and_emits_triggers(self):
        controller = self._controller()
        controller.set_rules([_rule("sh600519", threshold=5.0)])
        controller.start(interval_ms=50)
        self.assertTrue(controller.is_running())
        fired = wait_for(controller.alerts_triggered)
        self.assertTrue(fired, "alerts_triggered 未在超时内触发")
        triggered = fired[0][0]
        self.assertTrue(any(r.code == "sh600519" for r in triggered))

    def test_triggers_arrive_on_the_gui_thread(self):
        controller = self._controller()
        controller.set_rules([_rule("sh600519")])
        gui_thread = QtCore.QThread.currentThread()
        seen: list = []
        controller.alerts_triggered.connect(
            lambda _rules: seen.append(QtCore.QThread.currentThread())
        )
        controller.start(interval_ms=50)
        wait_for(controller.alerts_triggered)
        self.assertTrue(seen)
        self.assertEqual(seen[0], gui_thread)

    def test_stop_makes_late_results_of_the_old_generation_dropped(self):
        # RISK-005：stop 提升 generation，之前那代 worker 的迟到结果必须被丢弃、不再发信号。
        controller = self._controller()
        controller.set_rules([_rule("sh600519")])
        gen_before = controller.generation()
        controller.start(interval_ms=50)
        controller.stop()
        self.assertFalse(controller.is_running())
        self.assertGreater(controller.generation(), gen_before)  # generation 已递增
        # 停止后不应再有新触发累积（等一小段，确认安静）。
        seen: list = []
        controller.alerts_triggered.connect(lambda r: seen.append(r))
        wait_for(controller.alerts_triggered, timeout_ms=200)
        self.assertEqual(seen, [])

    def test_single_symbol_failure_keeps_monitoring(self):
        controller = self._controller(FakeProvider(fail_codes={"sh600519"}))
        controller.set_rules([_rule("sh600519"), _rule("sz000001")])
        controller.start(interval_ms=50)
        fired = wait_for(controller.alerts_triggered)
        self.assertTrue(fired)
        codes = {r.code for r in fired[0][0]}
        self.assertIn("sz000001", codes)  # 未失败的仍触发；监控未停


if __name__ == "__main__":
    unittest.main()
