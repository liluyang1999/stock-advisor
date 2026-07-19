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

from ...domain.models import AlertRule
from ...services.alert_monitor import run_alert_cycle
from ...services.workflow import MarketDataProvider


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
        self._generation = 0
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def generation(self) -> int:
        return self._generation

    def set_rules(self, rules: list[AlertRule]) -> None:
        self._rules = list(rules)

    def start(self, interval_ms: int = 60000) -> None:
        """开始周期监控。递增 generation 使任何在途的上一代结果失效（RISK-005）。"""
        self._generation += 1
        self._fired = set()
        self._running = True
        self._timer.start(interval_ms)
        self._tick()  # 立即跑一轮，不等第一个 interval

    def stop(self) -> None:
        """停止监控。递增 generation，使已提交但未完成的 worker 结果被丢弃（RISK-005）。"""
        self._generation += 1
        self._running = False
        self._timer.stop()

    def shutdown(self) -> None:
        self.stop()
        self._pool.waitForDone(5000)

    def _tick(self) -> None:
        signals = _CycleSignals()
        signals.done.connect(self._on_cycle_done)
        worker = _CycleWorker(
            self._generation, list(self._rules), self._provider, set(self._fired), signals
        )
        self._pool.start(worker)

    def _on_cycle_done(self, generation: int, newly: list, fired: set) -> None:
        # 迟到结果丢弃：generation 不匹配说明这轮属于已停止/已重启的上一代（RISK-005）。
        if generation != self._generation or not self._running:
            return
        self._fired = fired
        if newly:
            self.alerts_triggered.emit(newly)
