"""WorkerControllerBase 契约（WI-013 / ADR-0003）。

从**两个真实控制器**（AnalysisController、ScreenerController）逐行一致的生命周期骨架里提取的
基类——不是前瞻猜测，是 N=2 的实证共性：有界 QThreadPool、协作取消原语、运行标志、
is_running/cancel/shutdown。信号集合与 worker 编排体仍由各子类专有。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt, wait_for

if QtWidgets is not None:
    from qt_app.controllers.base import WorkerControllerBase


@requires_qt
class WorkerControllerBaseTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _controller(self):
        # 一个最小具体子类：submit 一个立即完成的 runnable，用 finished 信号回主线程。
        done = QtCore.QObject()
        signal = type("_S", (QtCore.QObject,), {"fired": QtCore.Signal(object)})()

        class _Demo(WorkerControllerBase):
            fired = QtCore.Signal(object)

            def start(self):
                self._begin()

                class _R(QtCore.QRunnable):
                    def __init__(inner, cancel, emit):
                        super().__init__()
                        inner._cancel = cancel
                        inner._emit = emit

                    def run(inner):
                        inner._emit(inner._cancel.is_cancelled())

                self._pool.start(_R(self._cancel, self._emit_done))

            def _emit_done(self, cancelled):
                self._end()
                self.fired.emit(cancelled)

        _ = (done, signal)
        controller = _Demo()
        self.addCleanup(controller.shutdown)
        return controller

    def test_is_running_toggles_across_the_lifecycle(self):
        controller = self._controller()
        self.assertFalse(controller.is_running())
        controller.start()
        self.assertTrue(controller.is_running())
        wait_for(controller.fired)
        self.assertFalse(controller.is_running())

    def test_bounded_thread_pool(self):
        controller = self._controller()
        self.assertLessEqual(controller._pool.maxThreadCount(), 4)

    def test_cancel_before_start_is_safe(self):
        controller = self._controller()
        controller.cancel()  # 尚无 _cancel，不应抛
        controller.start()
        wait_for(controller.fired)

    def test_shutdown_waits_and_is_idempotent(self):
        controller = self._controller()
        controller.start()
        wait_for(controller.fired)
        controller.shutdown()
        controller.shutdown()  # 二次调用安全


if __name__ == "__main__":
    unittest.main()
