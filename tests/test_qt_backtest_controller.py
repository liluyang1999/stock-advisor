"""回测后台调度：线程边界、去重、有界排队、缓存失效与失败恢复。"""

import sys
import threading
import unittest
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src"), str(Path(__file__).parent)]

from qt_test_helpers import QtCore, qt_app, requires_qt, wait_for

from domain.models import BacktestReport
from qt_app.controllers.backtest_controller import BacktestController


def report(level):
    return BacktestReport(level=level, horizon=5, sample_size=0, buy_hold_return=0, note="样本不足")


@requires_qt
class BacktestControllerTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _controller(self, compute):
        controller = BacktestController(compute=compute)
        self.addCleanup(controller.shutdown)
        return controller

    def test_compute_runs_off_gui_and_delivery_runs_on_gui(self):
        threads = []

        def compute(history, level):
            threads.append(QtCore.QThread.currentThread())
            return report(level)

        controller = self._controller(compute)
        delivered = []
        controller.ready.connect(lambda key: delivered.append(QtCore.QThread.currentThread()))
        self.assertIsNone(controller.request("sh600000", [], 3))
        self.assertTrue(wait_for(controller.ready))
        self.assertNotEqual(threads[0], self.app.thread())
        self.assertEqual(delivered, [self.app.thread()])
        self.assertEqual(controller.request("sh600000", [], 3), report(3))
        self.assertEqual(len(threads), 1)

    def test_repeated_selection_is_deduplicated_and_pending_work_is_bounded(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        def compute(history, level):
            calls.append(level)
            if len(calls) == 1:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test worker was not released")
            return report(level)

        controller = self._controller(compute)
        self.addCleanup(release.set)
        controller.request("A", [], 1)
        self.assertTrue(entered.wait(5))
        for _ in range(10):
            controller.request("A", [], 1)
        controller.request("B", [], 2)
        controller.request("C", [], 3)
        release.set()
        self.assertTrue(wait_for(controller.ready))
        if controller.request("C", [], 3) is None:
            self.assertTrue(wait_for(controller.ready))
        self.assertEqual(calls, [1, 3])

    def test_reset_discards_inflight_result_and_invalidates_cached_history(self):
        entered, release = threading.Event(), threading.Event()

        def compute(history, level):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test worker was not released")
            return report(level)

        controller = self._controller(compute)
        self.addCleanup(release.set)
        got = []
        controller.ready.connect(got.append)
        controller.request("A", [], 1)
        self.assertTrue(entered.wait(5))
        controller.reset()
        controller.request("B", [], 2)
        release.set()
        self.assertTrue(wait_for(controller.ready))
        self.assertEqual(got, [("B", 2)])
        controller.reset()
        self.assertIsNone(controller.request("B", [], 2))
        self.assertTrue(wait_for(controller.ready))

    def test_computation_failure_is_visible_and_the_next_request_can_succeed(self):
        def compute(history, level):
            if level == 1:
                raise ValueError("invalid history")
            return report(level)

        controller = self._controller(compute)
        controller.request("A", [], 1)
        self.assertTrue(wait_for(controller.ready))
        failed = controller.request("A", [], 1)
        self.assertFalse(failed.ok)
        self.assertIn("回测暂不可用", failed.message)
        controller.request("B", [], 2)
        self.assertTrue(wait_for(controller.ready))
        self.assertTrue(controller.request("B", [], 2).ok)

    def test_shutdown_is_idempotent_and_rejects_new_work(self):
        calls = []
        controller = self._controller(lambda history, level: calls.append(level) or report(level))
        controller.shutdown()
        controller.shutdown()
        self.assertIsNone(controller.request("A", [], 3))
        self.assertEqual(calls, [])

    def test_shutdown_reports_a_worker_that_has_not_drained(self):
        entered, release = threading.Event(), threading.Event()

        def compute(history, level):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test worker was not released")
            return report(level)

        controller = self._controller(compute)
        self.addCleanup(release.set)
        controller.request("A", [], 3)
        self.assertTrue(entered.wait(5))
        self.assertFalse(controller.shutdown(wait_ms=0))
        release.set()
        self.assertTrue(controller.shutdown(wait_ms=1000))
        self.assertFalse(controller.is_running())

    def test_default_worker_observes_cancellation_between_pure_steps(self):
        from unittest.mock import patch

        entered, release = threading.Event(), threading.Event()
        steps = []

        def computation(history, level):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test worker was not released")
            yield
            steps.append("should not resume after cancellation")
            return report(level)

        controller = BacktestController()
        self.addCleanup(controller.shutdown)
        self.addCleanup(release.set)
        with patch("qt_app.controllers.backtest_controller.backtest_steps", computation):
            controller.request("A", [], 3)
            self.assertTrue(entered.wait(5))
            controller.reset()
            release.set()
            self.assertTrue(controller.shutdown(wait_ms=1000))
        self.assertEqual(steps, [])


if __name__ == "__main__":
    unittest.main()
