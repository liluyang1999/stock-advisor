"""Qt 异步控制器的生命周期骨架基类（ADR-0003 / WI-013）。

从 `AnalysisController` 与 `ScreenerController` **逐行一致**的生命周期部分提取——是 N=2 的实证共性，
不是前瞻猜测（提取前两个控制器各自复制了这段 ~15 行）。基类只承担"线程池 + 协作取消 + 运行标志"
这套骨架；**信号集合、start 签名、worker 编排体仍由各子类专有**，因为那三样在两个样本里确实不同
（批量 vs 筛选的取消协议、信号名、编排入口）。

子类模式：`start()` 里先 `self._begin()`（重置取消原语、置运行中），提交 QRunnable；worker 完成时
在 GUI 线程槽里 `self._end()`（清运行中）再发自己的完成信号。
"""

from __future__ import annotations

from PySide6 import QtCore

from ...ports import ManualCancel
from ..workers import GenerationGuard

_MAX_CONCURRENCY = 4  # 有界并发（REQ-025 限并发面，避免一次性打满远端）
_SHUTDOWN_WAIT_MS = 5000


class WorkerControllerBase(QtCore.QObject):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QtCore.QThreadPool()
        self._pool.setMaxThreadCount(_MAX_CONCURRENCY)
        self._cancel: ManualCancel | None = None
        self._guard = GenerationGuard()  # RISK-005：迟到/重复启动结果的世代丢弃
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def generation(self) -> int:
        """当前世代号（测试/诊断用）。每次 start 递增。"""
        return self._guard.current

    def cancel(self) -> None:
        """请求协作取消当前轮；start 之前调用是安全的空操作。

        不递增世代：取消是"停下这一轮并交付它的（已取消）终态"，其完成信号仍应抵达以更新 UI；
        只有下一次 `start()`（重启/重复启动）才 supersede 世代、丢弃仍在途的上一轮结果。
        """
        if self._cancel is not None:
            self._cancel.cancel()

    def shutdown(self) -> None:
        """停止接收新工作并在有限时间内等待在跑的 worker 退出（ADR-0003 生命周期）。幂等。

        销毁前调用：等池排空后，任何仍排队的 queued signal 会因目标 QObject 被删而由 Qt 丢弃，
        故控件拆除竞态下不会有信号打到已释放对象上。
        """
        self.cancel()
        self._pool.waitForDone(_SHUTDOWN_WAIT_MS)

    # --- 子类在 start()/完成槽里调用的骨架钩子 ---

    def _begin(self) -> tuple[ManualCancel, int]:
        """开一轮：先取消上一轮在途 worker（重复启动/重启即 supersede 前一轮），再新建取消原语、
        递增世代、置运行中。返回 `(cancel, generation)`——cancel 交给 worker 协作查询，generation
        交给完成/进度闭包经 `_guarded` 做迟到丢弃。"""
        if self._cancel is not None:
            self._cancel.cancel()  # 上一轮 worker 下次查询取消即协作退出，其结果由世代守卫丢弃
        self._cancel = ManualCancel()
        self._running = True
        return self._cancel, self._guard.bump()

    def _end(self) -> None:
        """结束一轮：清运行中标志（在 GUI 线程的完成槽里调用）。"""
        self._running = False

    def _is_current(self, generation: int) -> bool:
        """`generation` 是否仍是当前世代。

        子类的 worker 信号把开轮拿到的 `generation` 作为**第一个参数**回传（QObject 绑定方法槽，
        保证跨线程 queued 交付），槽里先 `if not self._is_current(generation): return` 丢弃被
        supersede 的上一代迟到结果，再推进对外信号与运行标志（RISK-005 / 零迟到泄漏）。
        不用"把槽包成闭包"的写法：连到临时闭包会丢失 QObject 线程亲和、退化为直连甚至被 GC。
        """
        return self._guard.is_current(generation)
