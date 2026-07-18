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

_MAX_CONCURRENCY = 4  # 有界并发（REQ-025 限并发面，避免一次性打满远端）
_SHUTDOWN_WAIT_MS = 5000


class WorkerControllerBase(QtCore.QObject):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QtCore.QThreadPool()
        self._pool.setMaxThreadCount(_MAX_CONCURRENCY)
        self._cancel: ManualCancel | None = None
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        """请求协作取消；start 之前调用是安全的空操作。已完成结果由各编排自行保留。"""
        if self._cancel is not None:
            self._cancel.cancel()

    def shutdown(self) -> None:
        """停止接收新工作并在有限时间内等待在跑的 worker 退出（ADR-0003 生命周期）。幂等。"""
        self.cancel()
        self._pool.waitForDone(_SHUTDOWN_WAIT_MS)

    # --- 子类在 start()/完成槽里调用的骨架钩子 ---

    def _begin(self) -> ManualCancel:
        """开一轮：新建取消原语、置运行中，返回该原语供 worker 持有。"""
        self._cancel = ManualCancel()
        self._running = True
        return self._cancel

    def _end(self) -> None:
        """结束一轮：清运行中标志（在 GUI 线程的完成槽里调用）。"""
        self._running = False
