"""批量个股分析编排（REQ-001/010/013 / WI-010）。

**框架无关**：规范化→去重→逐只分析→单只失败隔离→协作取消，全是纯逻辑，不依赖 PySide6，
可离线确定性测试。Qt 层（`qt_app/controllers/analysis_controller.py`）只负责把这套编排放到
QThreadPool 并用信号回主线程——线程分发是 Qt 的事，编排规则是这里的事。

三条硬规则：
- REQ-001：最多 30 只，规范化、去重、校验；超限或空输入是**输入错误**，整批不启动。
- REQ-010：**单只失败绝不终止批量**——每只的异常被隔离成一个 not-ok 的 outcome，其余继续；
  用户可通过 cancel_token 安全停止，已完成的结果保留。
- REQ-013 的编排面：本模块不碰任何 QWidget；线程与主线程更新由 Qt 适配层负责。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from domain.models import STANDARD_LEVEL
from domain.symbols import parse_user_symbols
from ports import CancelToken, ManualCancel

from .workflow import AnalysisOutcome, MarketDataProvider, analyze_symbol

_NEVER_CANCELLED = ManualCancel()


@dataclass(frozen=True)
class BatchProgress:
    """一次进度回调的快照：刚完成第 `done` 只（共 `total` 只），附该只结果。"""

    done: int
    total: int
    outcome: AnalysisOutcome


@dataclass
class BatchReport:
    total: int = 0
    outcomes: list[AnalysisOutcome] = field(default_factory=list)
    cancelled: bool = False
    input_error: str = ""

    @property
    def success_count(self) -> int:
        return sum(1 for o in self.outcomes if o.ok)

    @property
    def failure_count(self) -> int:
        return sum(1 for o in self.outcomes if not o.ok)


def run_batch_analysis(
    text: str,
    provider: MarketDataProvider,
    *,
    level: int = STANDARD_LEVEL,
    cancel_token: CancelToken = _NEVER_CANCELLED,
    on_progress: Callable[[BatchProgress], None] | None = None,
) -> BatchReport:
    """规范化并逐只分析用户输入的一批代码，返回汇总报告。

    单只分析的任何异常都被隔离进该只的 `AnalysisOutcome.error`（analyze_symbol 已保证不外抛
    可展示错误），因此本循环不会因个别失败而中断——这是 REQ-010 的落点。取消在每只之前检查，
    已完成的结果保留在报告里。
    """

    try:
        symbols = parse_user_symbols(text)
    except ValueError as exc:
        # 规范化/去重/上限/空输入的校验失败：整批不启动（REQ-001）。
        return BatchReport(input_error=str(exc))

    report = BatchReport(total=len(symbols))
    for symbol in symbols:
        if cancel_token.is_cancelled():
            report.cancelled = True
            break
        outcome = analyze_symbol(symbol, provider, level)
        if cancel_token.is_cancelled():
            report.cancelled = True
            break
        report.outcomes.append(outcome)
        if on_progress is not None:
            on_progress(
                BatchProgress(done=len(report.outcomes), total=len(symbols), outcome=outcome)
            )
    report.cancelled = report.cancelled or cancel_token.is_cancelled()
    return report
