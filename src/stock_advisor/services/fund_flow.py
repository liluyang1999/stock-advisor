"""资金流按需拉取包装（REQ-007 / WI-017）。

资金流是**独立、可失败、不进核心分析**的辅助通道（见 NETWORK_RESILIENCE 数据源策略）。
`fetch_fund_flow` 全部源失败才抛 `MarketDataError`；本包装把成功与失败都收敛成一个可展示的
`FundFlowResult`——失败带 error、绝不外抛，因此任何资金流故障都不会污染核心分析路径。

框架无关：不依赖 PySide6，可离线测。Qt 层用 QThreadPool 异步调用它。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data.data_provider import MarketDataError
from ..domain.models import FundFlow
from ..domain.symbols import normalize_symbol


@dataclass(frozen=True)
class FundFlowResult:
    flow: FundFlow | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.flow is not None and not self.error


def fetch_fund_flow_result(code: str, provider, limit: int = 6) -> FundFlowResult:
    """按需拉取一只的资金流，把成功/失败都收敛成可展示结果——**绝不外抛**（REQ-007）。"""

    try:
        symbol = normalize_symbol(code)
    except ValueError as exc:
        return FundFlowResult(error=f"股票代码无效：{exc}")

    try:
        flow = provider.fetch_fund_flow(symbol, limit)
    except (MarketDataError, ValueError) as exc:
        return FundFlowResult(error=f"资金流暂不可用：{exc}")
    except Exception as exc:  # noqa: BLE001 - 资金流是可失败辅助通道，任何异常都不得逃逸污染核心
        return FundFlowResult(error=f"资金流获取失败：{exc}")
    return FundFlowResult(flow=flow)
