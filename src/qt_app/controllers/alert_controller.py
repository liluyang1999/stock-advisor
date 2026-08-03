"""预警监控的 Qt 控制器（REQ-006/010/013 / WI-016 / ADR-0003 / RISK-005）。

与批量/筛选控制器不同，这是**周期性**监控：一个 `QTimer` 每隔 interval 把一轮 `run_alert_cycle`
提交到 `QThreadPool`，新触发经 queued signal 回 GUI 线程。因为是长期反复跑，必须防"迟到结果覆盖
新状态"（RISK-005）：每轮携带一个 **generation** 计数，`stop()`/`start()` 都递增它；worker 完成时
若其 generation 已过期（用户已停止或重启），结果被丢弃、不发信号、不推进 fired 状态。

单只刷新失败被 `run_alert_cycle` 隔离，一条规则/一只失败不停监控（REQ-010）；耗时刷新在工作线程，
GUI 不阻塞（REQ-013）。fired 边沿状态由控制器持有、跨轮传递。
"""

from __future__ import annotations

from PySide6 import QtCore

from domain.models import AlertRule
from ports import ManualCancel
from services.alert_monitor import run_alert_cycle
from services.workflow import MarketDataProvider

from ..workers import GenerationGuard


class _CycleSignals(QtCore.QObject):
    done = QtCore.Signal(int, object, object)  # generation, newly_fired(list), fired(set)


class _CycleWorker(QtCore.QRunnable):
    def __init__(self, generation, rules, provider, fired, signals) -> None:
        super().__init__()
        self._generation = generation
        self._rules = rules
        self._provider = provider
        self._fired = fired
        self._signals = signals

    def run(self) -> None:
        newly, fired = run_alert_cycle(self._rules, self._provider, self._fired)
        self._signals.done.emit(self._generation, newly, fired)


class AlertController(QtCore.QObject):
    """GUI 侧入口。set_rules 设规则，start/stop 驱动周期监控，connect alerts_triggered 收新触发。"""

    alerts_triggered = QtCore.Signal(object)  # list[AlertRule]（本轮新触发）

    def __init__(self, provider: MarketDataProvider, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._pool = QtCore.QThreadPool()
        self._pool.setMaxThreadCount(2)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._rules: list[AlertRule] = []
        self._fired: set = set()
        self._guard = GenerationGuard()  # RISK-005：与 WorkerControllerBase 共用同一世代守卫原语
        self._running = False
        # 在途守卫：一轮跑得比 interval 久时，后续 tick 会重叠。若不拦，多个重叠周期共用同一份
        # 旧 fired 快照——边沿触发的预警会每轮重复触发，且 fired 被后完成的那轮覆盖。同一时刻只允
        # 许一轮在途。
        self._in_flight = False
        # 协作取消令牌：交给传输层，`stop()` 一翻就能打断**在途**那一轮轮询。少了它，关窗时
        # `shutdown()` 的 waitForDone 要一直等到该轮跑满总 deadline 才排空得掉。
        self._cancel: ManualCancel | None = None

    def is_running(self) -> bool:
        return self._running

    def generation(self) -> int:
        return self._guard.current

    def set_rules(self, rules: list[AlertRule]) -> None:
        self._rules = list(rules)

    def start(self, interval_ms: int = 60000) -> None:
        """开始周期监控。递增 generation 使任何在途的上一代结果失效（RISK-005）。"""
        self._guard.bump()
        self._fired = set()
        self._running = True
        self._in_flight = False  # 新一轮监控从"无在途"开始，不被上一次遗留的标志挡住
        self._cancel = ManualCancel()
        binder = getattr(self._provider, "set_cancel_token", None)
        if callable(binder):
            binder(self._cancel)
        self._timer.start(interval_ms)
        self._tick()  # 立即跑一轮，不等第一个 interval

    def stop(self) -> None:
        """停止监控。递增 generation，使已提交但未完成的 worker 结果被丢弃（RISK-005）。"""
        self._guard.bump()
        self._running = False
        self._timer.stop()
        if self._cancel is not None:
            self._cancel.cancel()  # 打断在途那一轮，让 shutdown 能按时排空

    def shutdown(self) -> None:
        self.stop()
        self._pool.waitForDone(5000)

    def _tick(self) -> None:
        if self._in_flight:
            # 上一轮还没跑完：跳过这一拍，避免重叠周期基于同一份旧 fired 重复触发。
            return
        self._in_flight = True
        signals = _CycleSignals()
        signals.done.connect(self._on_cycle_done)
        worker = _CycleWorker(
            self._guard.current, list(self._rules), self._provider, set(self._fired), signals
        )
        self._pool.start(worker)

    def _on_cycle_done(self, generation: int, newly: list, fired: set) -> None:
        # 迟到结果丢弃：generation 不匹配说明这轮属于已停止/已重启的上一代（RISK-005）。此时不清
        # in_flight——它属于当前代那一轮在途 worker（stop→start 已在 start 里重置过），迟到的旧代
        # worker 无权放行下一拍。
        if not self._guard.is_current(generation) or not self._running:
            return
        self._in_flight = False  # 当前代这一轮已结束，放行下一拍
        self._fired = fired
        if newly:
            self.alerts_triggered.emit(newly)
