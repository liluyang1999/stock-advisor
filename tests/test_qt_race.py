"""异步控制器竞态收敛：取消 / 迟到丢弃 / 控件拆除 / 重复启动（REQ-010/013/025 / WI-019 / TEST-RACE-001）。

DoD：取消、迟到结果丢弃、控件拆除竞态、重复启动四类场景全部通过，**零迟到泄漏**——被后续 start
supersede 的上一轮，其进度/单项/完成信号绝不抵达对外接口。

确定性来源：世代号随每次 `start()` 递增（GUI 线程内同步发生），而 worker 的信号是 queued——只在
事件循环转起来时才在 GUI 线程被处理。测试在"转事件循环之前"就完成两次 start，故任何上一轮的
queued 结果被处理时世代早已过期，必被丢弃。无需 sleep 去命中时序窗口。
"""

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt, wait_for
from test_engine import FakeProvider, fake_quote

from stock_advisor.domain.models import FundFlow

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.analysis_controller import AnalysisController
    from stock_advisor.qt_app.controllers.fund_flow_controller import FundFlowController


def _drain(ms: int = 200) -> None:
    """把事件循环转 `ms` 毫秒，处理完所有 queued 信号（含被守卫丢弃的上一代结果）后退出。

    这是一个上界，不是"等某个时序"：断言的是"零泄漏"这个对所有交错都成立的不变量，`_drain` 只是
    给所有在途 worker 的 queued 信号一个被处理（并被丢弃或交付）的机会。
    """
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


class _GatedProvider:
    """fetch_quote 阻塞在一个 Event 上直到 open()，用于制造"worker 确实在途"的确定窗口。"""

    def __init__(self) -> None:
        self._gate = threading.Event()
        self._lock = threading.Lock()
        self.calls: list[str] = []

    def open(self) -> None:
        self._gate.set()

    def fetch_quote(self, symbol):
        with self._lock:
            self.calls.append(symbol.normalized)
        self._gate.wait(timeout=3)  # 兜底 3s 防止 open 漏调导致挂死
        return fake_quote(symbol)

    def fetch_history(self, symbol):
        return []


@requires_qt
class DuplicateLaunchTests(unittest.TestCase):
    """重复启动：后一次 start supersede 前一轮，前一轮结果零泄漏。"""

    def setUp(self):
        self.app = qt_app()

    def _controller(self, provider):
        controller = AnalysisController(provider)
        self.addCleanup(controller.shutdown)
        return controller

    def test_generation_increments_on_each_start(self):
        controller = self._controller(FakeProvider())
        self.assertEqual(controller.generation(), 0)
        controller.start("600000")
        self.assertEqual(controller.generation(), 1)
        controller.start("600001")
        self.assertEqual(controller.generation(), 2)

    def test_only_the_latest_cycle_delivers_a_terminal(self):
        controller = self._controller(FakeProvider())
        finished: list = []
        controller.batch_finished.connect(lambda r: finished.append(r))
        controller.start("600000")  # 第 1 轮（将被 supersede）
        controller.start("600001 600002")  # 第 2 轮，在事件循环转起来前就 supersede 第 1 轮
        wait_for(controller.batch_finished)  # 第一个"被交付"的终态必是第 2 轮（第 1 轮被丢弃）
        _drain(150)  # 再给第 1 轮的迟到终态一个抵达机会——它必须被丢弃
        self.assertEqual(len(finished), 1, "被 supersede 的上一轮终态泄漏了")
        self.assertEqual(finished[0].success_count, 2)  # 是第 2 轮（600001 600002）

    def test_superseded_cycle_symbols_never_reach_the_view(self):
        controller = self._controller(FakeProvider())
        analyzed: list = []
        controller.symbol_analyzed.connect(lambda o: analyzed.append(o.symbol.normalized))
        controller.start("600000")  # 第 1 轮
        controller.start("600001 600002")  # 第 2 轮 supersede
        wait_for(controller.batch_finished)
        _drain(150)
        codes = set(analyzed)
        self.assertNotIn("sh600000", codes)  # 第 1 轮的单项被丢弃，不污染新一轮表格
        self.assertEqual(codes, {"sh600001", "sh600002"})  # 只有第 2 轮的单项抵达视图


@requires_qt
class CancellationTests(unittest.TestCase):
    """取消：交付本轮的已取消终态（取消不 supersede 世代），此后不再有新结果。"""

    def setUp(self):
        self.app = qt_app()

    def test_cancel_delivers_a_cancelled_terminal_of_the_current_cycle(self):
        provider = _GatedProvider()
        controller = AnalysisController(provider)
        self.addCleanup(controller.shutdown)
        controller.start("600000 600001 600002")  # worker 阻塞在 gate 上（在途）
        controller.cancel()  # 请求协作取消（不递增世代）
        provider.open()  # 放行：worker 取回首只后查询到取消，收敛出已取消终态
        got = wait_for(controller.batch_finished)
        self.assertTrue(got)
        self.assertTrue(got[0][0].cancelled)  # 当前世代的已取消终态被交付（更新 UI）
        self.assertFalse(controller.is_running())


@requires_qt
class TeardownTests(unittest.TestCase):
    """控件拆除：shutdown 取消在途并排空线程池（幂等）；排空后销毁控制器干净、不崩。

    说明：控制器自持 `QThreadPool`，其析构会 `waitForDone` 阻塞到在途 worker 结束——所以正确的
    拆除次序是"先 `shutdown()` 排空、再销毁"，页面清理即应如此（这也是 in-flight 直接删不会崩、
    只会阻塞的原因）。这里验证的正是这条契约路径。
    """

    def setUp(self):
        self.app = qt_app()

    def test_shutdown_cancels_inflight_and_drains(self):
        provider = _GatedProvider()
        controller = AnalysisController(provider)
        controller.start("600000 600001")  # 在途，阻塞在 gate 上
        provider.open()  # 放行让 worker 能退出，shutdown 才能在限时内排空
        controller.shutdown()  # 请求取消 + waitForDone 排空
        _drain(150)  # 处理排空后 queued 的终态
        self.assertFalse(controller.is_running())  # 排空 + 终态处理后不再运行

    def test_shutdown_is_idempotent(self):
        provider = _GatedProvider()
        controller = AnalysisController(provider)
        controller.start("600000")
        provider.open()
        controller.shutdown()
        controller.shutdown()  # 二次调用不崩、不挂
        self.assertIsNotNone(QtWidgets.QApplication.instance())  # 进程仍在

    def test_shutdown_then_delete_is_clean(self):
        provider = _GatedProvider()
        controller = AnalysisController(provider)
        delivered: list = []
        controller.batch_finished.connect(lambda r: delivered.append(r))
        controller.start("600000")  # 在途
        provider.open()  # 放行
        controller.shutdown()  # 池已排空，无在途 worker
        controller.deleteLater()  # 排空后销毁：安全，不阻塞、不崩
        _drain(150)  # 处理 DeferredDelete
        self.assertIsNotNone(QtWidgets.QApplication.instance())  # 拆除后进程仍在


@requires_qt
class FundFlowDuplicateLaunchTests(unittest.TestCase):
    """资金流连点两次：后一次 supersede 前一次，前一次的迟到结果零泄漏。"""

    def setUp(self):
        self.app = qt_app()

    class _OkProvider:
        def __init__(self, tag):
            self._tag = tag

        def fetch_fund_flow(self, symbol, limit=6):
            return FundFlow(today_main=float(self._tag), main_5d=2.0e8, recent=[])

    def test_only_the_latest_query_delivers(self):
        controller = FundFlowController(self._OkProvider(2))
        self.addCleanup(controller.shutdown)
        ready: list = []
        controller.fund_flow_ready.connect(lambda r: ready.append(r))
        controller.start("600000")  # 第 1 次查询
        controller.start("600519")  # 第 2 次 supersede 第 1 次
        wait_for(controller.fund_flow_ready)
        _drain(150)
        self.assertEqual(len(ready), 1)  # 只交付最后一次；上一次迟到结果被丢弃


if __name__ == "__main__":
    unittest.main()
