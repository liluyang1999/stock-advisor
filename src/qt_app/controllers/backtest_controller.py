"""按需后台回测：一项在跑、一项最新等待；缓存只属于当前分析批次。"""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6 import QtCore

from domain.backtest import backtest_steps
from domain.models import BacktestReport, DailyBar
from observability import get_logger

_Compute = Callable[[list[DailyBar], int], BacktestReport]
_Key = tuple[str, int]
_CACHE_LIMIT = 150  # 一批最多 30 只，每只五档；换批或清空即失效。


class _Signals(QtCore.QObject):
    finished = QtCore.Signal(int, object, object)


class _Worker(QtCore.QRunnable):
    def __init__(
        self,
        generation: int,
        key: _Key,
        history: list[DailyBar],
        compute: _Compute | None,
        signals: _Signals,
        cancel: Event,
    ) -> None:
        super().__init__()
        self.generation, self.key = generation, key
        self.history, self.compute, self.signals = history, compute, signals
        self.cancel = cancel

    def run(self) -> None:
        report = None
        try:
            if self.compute is not None:
                report = self.compute(self.history, self.key[1])
            else:
                steps = backtest_steps(self.history, self.key[1])
                try:
                    while not self.cancel.is_set():
                        try:
                            next(steps)
                        except StopIteration as completed:
                            report = completed.value
                            break
                finally:
                    steps.close()
        except Exception:  # worker 边界：必须交付失败终态，不能让页面永久停在“计算中”。
            get_logger("backtest").error("后台回测失败")
            report = BacktestReport(
                level=self.key[1],
                horizon=5,
                sample_size=0,
                buy_hold_return=0,
                note="计算失败",
                ok=False,
                message="回测暂不可用，请重新分析后重试。",
            )
        self.signals.finished.emit(
            self.generation, self.key, None if self.cancel.is_set() else report
        )


class BacktestController(QtCore.QObject):
    """只消费已获取的历史，不持有 provider、不联网，所有缓存与信号交付在 GUI 线程。

    快速切档不会向线程池塞入无限多项工作。当前计算结束后只执行最后一次选择；旧批次结果
    按世代丢弃。正常返回的报告（包括样本不足）可复用，改本金不触发回测。
    """

    ready = QtCore.Signal(object)  # (normalized symbol, level)

    def __init__(
        self, parent: QtCore.QObject | None = None, *, compute: _Compute | None = None
    ) -> None:
        super().__init__(parent)
        self._compute = compute
        self._pool = QtCore.QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._signals = _Signals(self)
        self._signals.finished.connect(self._finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._cache: dict[_Key, BacktestReport] = {}
        self._generation = 0
        self._active: tuple[int, _Key] | None = None
        self._pending: tuple[_Key, list[DailyBar]] | None = None
        self._closed = False
        self._cancel: Event | None = None

    def request(self, code: str, history: list[DailyBar], level: int) -> BacktestReport | None:
        if self._closed:
            return None
        key = (code, level)
        if key in self._cache:
            self._pending = None
            return self._cache[key]
        if self._active == (self._generation, key):
            self._pending = None
            return None
        self._pending = (key, list(history))
        self._launch_pending()
        return None

    def reset(self) -> None:
        """新批次/清空：取消尚未开始的计算，并拒收旧历史的迟到报告。"""
        self._generation += 1
        self._pending = None
        self._cache.clear()
        if self._cancel is not None:
            self._cancel.set()

    def is_running(self) -> bool:
        return self._active is not None or self._pending is not None

    def shutdown(self, wait_ms: int = 5000) -> bool:
        self._closed = True
        self.reset()
        drained = self._pool.waitForDone(wait_ms)
        if drained:
            self._active = None
        return drained

    def _launch_pending(self) -> None:
        if self._active is not None or self._pending is None or self._closed:
            return
        key, history = self._pending
        self._pending = None
        self._active = (self._generation, key)
        self._cancel = Event()
        self._pool.start(
            _Worker(self._generation, key, history, self._compute, self._signals, self._cancel)
        )

    @QtCore.Slot(int, object, object)
    def _finished(self, generation: int, key: _Key, report: BacktestReport | None) -> None:
        self._active = None
        if report is not None and generation == self._generation and not self._closed:
            if len(self._cache) >= _CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = report
            self.ready.emit(key)
        self._launch_pending()
