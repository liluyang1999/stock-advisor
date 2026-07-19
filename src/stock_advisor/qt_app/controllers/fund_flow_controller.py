"""资金流按需拉取的 Qt 异步控制器（REQ-007 / WI-017 / ADR-0003）。

生命周期骨架继承 `WorkerControllerBase`（第三个复用者，进一步印证 N=2 抽象的正确性）。资金流是
独立可失败通道：`fetch_fund_flow_result` 已把失败收敛成可展示结果、绝不外抛，故本控制器把它提交到
QThreadPool，结果（成功或降级）经 queued signal 回 GUI 线程——资金流故障不阻塞、不污染核心分析。
"""

from __future__ import annotations

from PySide6 import QtCore

from ...services.fund_flow import FundFlowResult, fetch_fund_flow_result
from .base import WorkerControllerBase


class _FlowSignals(QtCore.QObject):
    done = QtCore.Signal(object)  # FundFlowResult


class _FlowWorker(QtCore.QRunnable):
    def __init__(self, code, provider, signals) -> None:
        super().__init__()
        self._code = code
        self._provider = provider
        self._signals = signals

    def run(self) -> None:
        self._signals.done.emit(fetch_fund_flow_result(self._code, self._provider))


class FundFlowController(WorkerControllerBase):
    """connect fund_flow_ready 收结果（成功或降级）；start(code) 驱动。"""

    fund_flow_ready = QtCore.Signal(object)  # FundFlowResult

    def __init__(self, provider, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._provider = provider

    def start(self, code: str) -> None:
        """按需拉取一只的资金流并立即返回；结果经信号到达（成功或可见降级）。"""
        self._begin()
        signals = _FlowSignals()
        signals.done.connect(self._on_done)
        self._pool.start(_FlowWorker(code, self._provider, signals))

    def _on_done(self, result: FundFlowResult) -> None:
        self._end()
        self.fund_flow_ready.emit(result)
