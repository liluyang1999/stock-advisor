"""把有界传输接进出货路径（REQ-024/025/026 · WI-033）。

`BoundedUrllibProvider` 用 envelope 表达结果（成功带数据、失败结构上不带数据、另带取消与分页完整度），
而编排层 `services.workflow` / `services.fund_flow` 要的是老合同：**拿到数据，或抛 `MarketDataError`**。
本适配器只做这层翻译，于是整条出货路径一次性拿到：

* **总 deadline**——一个预算覆盖所有重试与备用源，不再是"每个源各拿一份完整预算"（此前个股历史
  最坏要跑 4 源 × 3 重试 × 8 s ≈ 100 s，取消与关窗期间界面像卡死）；
* **协作取消**——在途请求能被打断（`set_cancel_token`），而不是只能在两只股票之间检查；
* **字节上限**——响应体读取有天花板，异常大的响应不会把内存撑爆；
* **真实的分页完整度**——这是用户最直接受益的一条，见下。

**为什么 `market_completeness()` 是本次改动的重点**：`workflow._provider_completeness` 用 duck-typing
取这个方法，取不到就默认「完整」。老 provider 没有它，于是全市场拉取在后续页失败时**静默返回半个
市场**，`ScreenReport.completeness.is_complete` 仍是 True，REQ-026 那条"非全市场结果"的警告永远不会
触发——用户以为自己在全市场里选股，其实只在拿到的那部分里。适配器把传输层早已算好的完整度如实
交出去，这条链路才真正闭合。

适配器**不**放宽任何契约：失败一律抛错，绝不把失败 envelope 翻译成空列表或零值（REQ-024 零伪造）。
"""

from __future__ import annotations

from domain.models import DailyBar, FundFlow, MarketSnapshot, Quote, StockSymbol
from ports import CancelToken, Completeness, ManualCancel, TransportOutcome

from .bounded_transport import BoundedUrllibProvider
from .data_provider import MarketDataError

# 永不取消的哨兵：让"没设过取消令牌"与"设了一个未取消的令牌"走同一条代码路径。
_NEVER_CANCELLED = ManualCancel()


def _unwrap[T](outcome: TransportOutcome[T], what: str) -> T:
    """envelope → 数据，失败则抛 `MarketDataError`。

    失败的 envelope 结构上就没有 data，所以这里不存在"把半真数据放行"的可能；取消也走同一条
    失败路径（对调用方而言"这次没有数据"是同一件事，原因写在消息里）。
    """

    if not outcome.succeeded or outcome.data is None:
        reason = outcome.message or "未知原因"
        raise MarketDataError(f"{what}失败：{reason}")
    return outcome.data


class BoundedMarketDataProvider:
    """出货用的 provider：内部是有界传输，对外是编排层认识的老合同。"""

    def __init__(self, inner: BoundedUrllibProvider | None = None) -> None:
        self._inner = inner or BoundedUrllibProvider()
        self._cancel: CancelToken = _NEVER_CANCELLED
        # 最近一次**成功**全市场抓取的完整度。还没抓过时是默认值（无信息即完整），
        # 免得在用户还没选过股时就谎报残缺。
        self._completeness = Completeness()

    # --- 取消 ---

    def set_cancel_token(self, token: CancelToken | None) -> None:
        """挂上/摘下协作取消令牌。控制器在发起新一轮前设，取消时令牌一翻，在途请求即中断。"""

        self._cancel = token or _NEVER_CANCELLED

    # --- 完整度（REQ-026） ---

    def market_completeness(self) -> Completeness:
        """最近一次成功全市场抓取的分页完整度。`workflow._provider_completeness` 按名取用。"""

        return self._completeness

    # --- 四个取数 port ---

    def fetch_quote(self, symbol: StockSymbol) -> Quote:
        return _unwrap(self._inner.fetch_quote(symbol, cancel_token=self._cancel), "实时行情获取")

    def fetch_history(self, symbol: StockSymbol, limit: int = 120) -> list[DailyBar]:
        return _unwrap(
            self._inner.fetch_history(symbol, limit, cancel_token=self._cancel), "历史日线获取"
        )

    def fetch_fund_flow(self, symbol: StockSymbol, limit: int = 6) -> FundFlow:
        return _unwrap(
            self._inner.fetch_fund_flow(symbol, limit, cancel_token=self._cancel), "资金流获取"
        )

    def fetch_market_snapshot(
        self, page_size: int = 500, max_pages: int = 20
    ) -> list[MarketSnapshot]:
        outcome = self._inner.fetch_market_snapshot(page_size, max_pages, cancel_token=self._cancel)
        rows = _unwrap(outcome, "全市场快照获取")
        # 只在成功后记录：整轮失败时调用方拿到的是异常，此时没有"这批市场数据有多完整"可言，
        # 保留上一轮的真实值比写一个假的"完整"诚实。
        self._completeness = outcome.completeness
        return rows
