"""个股批量分析的 Qt 异步控制器（REQ-001/010/013 / WI-010 / ADR-0003）。

职责边界：**编排规则不在这里**——规范化/去重/单只失败隔离/取消全在框架无关的
`services.batch.run_batch_analysis`。本控制器只做 ADR-0003 的线程分发：把那套编排提交到
`QThreadPool` 的一个 `QRunnable`，让它在 GUI 线程之外运行（REQ-013：耗时任务不阻塞 GUI），
再把进度/单只结果/完成经 **queued signal** 送回 GUI 线程（REQ-013：QWidget 只在主线程更新）。

取消用框架无关的 `ManualCancel`（协作取消，编排循环在每只前查询），与 ADR-0003 的迁移期
`QThreadPool` 包装取向一致。
"""

from __future__ import annotations

from PySide6 import QtCore

from ...ports import ManualCancel
from ...services.batch import BatchProgress, BatchReport, run_batch_analysis
from ...services.workflow import AnalysisOutcome, MarketDataProvider
from .base import WorkerControllerBase


class _BatchSignals(QtCore.QObject):
    """QRunnable 不能带信号，故信号集中在这个 QObject 上，由 worker 持有并发射。"""

    progress = QtCore.Signal(object)  # BatchProgress
    symbol_analyzed = QtCore.Signal(object)  # AnalysisOutcome
    finished = QtCore.Signal(object)  # BatchReport


class _BatchWorker(QtCore.QRunnable):
    def __init__(
        self,
        text: str,
        provider: MarketDataProvider,
        level: int,
        cancel: ManualCancel,
        signals: _BatchSignals,
    ) -> None:
        super().__init__()
        self._text = text
        self._provider = provider
        self._level = level
        self._cancel = cancel
        self._signals = signals

    def run(self) -> None:  # 在 QThreadPool 的工作线程上执行，绝不碰 QWidget
        def _emit_progress(progress: BatchProgress) -> None:
            self._signals.progress.emit(progress)
            self._signals.symbol_analyzed.emit(progress.outcome)

        report = run_batch_analysis(
            self._text,
            self._provider,
            level=self._level,
            cancel_token=self._cancel,
            on_progress=_emit_progress,
        )
        self._signals.finished.emit(report)


class AnalysisController(WorkerControllerBase):
    """GUI 侧的入口。connect 这些信号来更新视图；调用 start/cancel 驱动。

    生命周期骨架（线程池/取消/运行标志/is_running/cancel/shutdown）继承自 WorkerControllerBase；
    本类只保留批量分析专有的信号集合、start 签名与 worker 编排。

    信号（均经 queued connection 回到本对象所在的 GUI 线程）：
    - `progress(BatchProgress)`：每完成一只
    - `symbol_analyzed(AnalysisOutcome)`：每只的结果
    - `batch_finished(BatchReport)`：整批完成（含输入错误/取消的情形）
    """

    progress = QtCore.Signal(object)
    symbol_analyzed = QtCore.Signal(object)
    batch_finished = QtCore.Signal(object)

    def __init__(self, provider: MarketDataProvider, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._provider = provider

    def start(self, text: str, level: int = 3) -> None:
        """提交一次批量分析并**立即返回**；结果稍后经信号到达（REQ-013 不阻塞 GUI）。"""

        cancel = self._begin()
        signals = _BatchSignals()
        signals.progress.connect(self._on_progress)
        signals.symbol_analyzed.connect(self._on_symbol)
        signals.finished.connect(self._on_finished)
        worker = _BatchWorker(text, self._provider, level, cancel, signals)
        self._pool.start(worker)

    # --- 以下槽在 GUI 线程执行（queued connection），负责把 worker 信号转发为对外信号 ---

    def _on_progress(self, progress: BatchProgress) -> None:
        self.progress.emit(progress)

    def _on_symbol(self, outcome: AnalysisOutcome) -> None:
        self.symbol_analyzed.emit(outcome)

    def _on_finished(self, report: BatchReport) -> None:
        self._end()
        self.batch_finished.emit(report)
