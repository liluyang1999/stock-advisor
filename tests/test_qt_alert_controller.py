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

from domain.models import AlertRule

if QtWidgets is not None:
    from qt_app.controllers.alert_controller import AlertController


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

    def test_overlapping_ticks_while_in_flight_start_no_extra_cycle(self):
        # 慢周期（一轮跑得比 interval 久）时，定时器后续的 tick 必须被在途守卫跳过：否则多个
        # 重叠周期共用同一份旧 fired 快照，边沿触发的预警每轮重复触发、fired 被后完成者覆盖。
        # done 是跨线程 queued 信号，未派发事件循环前不会清 in_flight，故 start() 后同步再 _tick()
        # 时该轮仍在途——用 _CycleWorker 构造计数确定性地断言"没有开启第二轮"。
        import qt_app.controllers.alert_controller as ac

        created: list = []
        original = ac._CycleWorker

        def _counting(*args, **kwargs):
            created.append(1)
            return original(*args, **kwargs)

        ac._CycleWorker = _counting
        self.addCleanup(lambda: setattr(ac, "_CycleWorker", original))

        controller = self._controller()
        controller.set_rules([_rule("sh600519")])
        controller.start(
            interval_ms=10_000
        )  # 立即跑一轮(cycle A)；大 interval 避免定时器自动再 tick
        controller._tick()  # 模拟在途期间的定时器 tick
        controller._tick()
        self.assertEqual(len(created), 1, "在途一轮期间的额外 tick 必须被跳过，不得开启重叠周期")

    def test_guard_releases_after_a_cycle_completes(self):
        # 守卫不能过度阻塞：一轮完成（_on_cycle_done 派发、清 in_flight）后，后续 tick 必须能开新周期，
        # 否则监控会在第一轮后永久卡死。
        import qt_app.controllers.alert_controller as ac

        controller = self._controller()
        controller.set_rules([_rule("sh600519")])
        controller.start(interval_ms=10_000)
        wait_for(controller.alerts_triggered)  # 等 A 完成并派发 _on_cycle_done → in_flight 应已清

        created: list = []
        original = ac._CycleWorker

        def _counting(*args, **kwargs):
            created.append(1)
            return original(*args, **kwargs)

        ac._CycleWorker = _counting
        self.addCleanup(lambda: setattr(ac, "_CycleWorker", original))

        controller._tick()
        self.assertEqual(len(created), 1, "一轮完成后守卫必须放行，后续 tick 能开启新周期")


if __name__ == "__main__":
    unittest.main()
