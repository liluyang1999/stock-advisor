"""全市场筛选的 Qt 异步控制器（REQ-002/013 / WI-013 / ADR-0003）。

与 `AnalysisController` 同构：编排规则在框架无关的 `services.screener_run.run_screen`，本控制器只做
ADR-0003 的线程分发——把编排提交到 `QThreadPool` 的 `QRunnable`，结果经 queued signal 回 GUI 线程。

先与 AnalysisController 保持"复制而非共享"：两者的取消协议不同（批量 `is_cancelled` vs 筛选
`is_set`，均由 `ManualCancel` 满足）、信号集合不同、worker 编排体不同。待两个具体控制器都落地、
真实共性显形后，再从**两个样本**里提取生命周期骨架（见 loop 进度记录的 N=2 触发点）。
"""

from __future__ import annotations

from PySide6 import QtCore

from ...ports import ManualCancel
from ...services.screener_run import run_screen
from ...services.workflow import Recommendation, ScreeningProvider, ScreenReport
from .base import WorkerControllerBase


class _ScreenSignals(QtCore.QObject):
    # 第一个参数是开轮世代号，供控制器丢弃被后续 start supersede 的上一轮迟到结果（RISK-005）。
    progress = QtCore.Signal(int, object)  # generation, Recommendation
    finished = QtCore.Signal(int, object)  # generation, ScreenReport


class _ScreenWorker(QtCore.QRunnable):
    def __init__(
        self,
        provider: ScreeningProvider,
        preset_key: str,
        tunables: dict[str, float],
        deep: bool,
        level: int,
        generation: int,
        cancel: ManualCancel,
        signals: _ScreenSignals,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._preset_key = preset_key
        self._tunables = tunables
        self._deep = deep
        self._level = level
        self._generation = generation
        self._cancel = cancel
        self._signals = signals

    def run(self) -> None:  # 在工作线程执行，绝不碰 QWidget
        def _progress(_rank: int, _total: int, rec: Recommendation) -> None:
            self._signals.progress.emit(self._generation, rec)

        report = run_screen(
            self._provider,
            self._preset_key,
            self._tunables,
            deep=self._deep,
            cancel_token=self._cancel,
            level=self._level,
            progress_cb=_progress,
        )
        self._signals.finished.emit(self._generation, report)


class ScreenerController(WorkerControllerBase):
    """GUI 侧入口。connect 信号更新视图；start/cancel 驱动。

    生命周期骨架继承自 WorkerControllerBase；本类只保留筛选专有的信号集合、start 签名与 worker。

    信号（经 queued connection 回 GUI 线程）：
    - `recommendation(Recommendation)`：每完成一只 TopN 深度分析
    - `screen_finished(ScreenReport)`：整轮筛选完成（含输入错误/取消）
    """

    recommendation = QtCore.Signal(object)
    screen_finished = QtCore.Signal(object)

    def __init__(self, provider: ScreeningProvider, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._provider = provider

    def start(
        self, preset_key: str, tunables: dict[str, float], deep: bool = True, level: int = 3
    ) -> None:
        """提交一次筛选并立即返回；结果稍后经信号到达（REQ-013 不阻塞 GUI）。"""

        cancel, gen = self._begin()
        signals = _ScreenSignals()
        signals.progress.connect(self._on_progress)
        signals.finished.connect(self._on_finished)
        worker = _ScreenWorker(
            self._provider, preset_key, dict(tunables), deep, level, gen, cancel, signals
        )
        self._pool.start(worker)

    # 每个槽先按世代号丢弃被后续 start supersede 的上一轮迟到结果（RISK-005 / 零迟到泄漏）。

    def _on_progress(self, generation: int, rec: Recommendation) -> None:
        if not self._is_current(generation):
            return
        self.recommendation.emit(rec)

    def _on_finished(self, generation: int, report: ScreenReport) -> None:
        if not self._is_current(generation):
            return  # 迟到：上一轮已被 supersede，丢弃其完成信号
        self._end()
        self.screen_finished.emit(report)
