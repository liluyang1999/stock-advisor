"""有界 urllib 迁移适配器：让现有同步 urllib 取数走 WI-009 的 port 合同（REQ-025 / REQ-026 / WI-026）。

`EastmoneyProvider` 能取到数，但它不满足 ADR-0003 定下的传输合同，差四件事：

1. **没有总 deadline。** `_request` 每次调用重新获得 `max_retries` 次重试外加退避 sleep，而
   `fetch_quote` 会依次试主源和备用源——于是"一次取数最久多久"没有上界，源越多越久。合同要求
   一个 deadline 覆盖所有重试与备用源。
2. **不可取消。** 用户点了停止，在途请求仍会把重试跑完。
3. **不分类。** 所有失败塌缩成 `MarketDataError`，调用方无法区分"网络抖动可换源重试"和"响应内容
   不合契约，换源也没用"。
4. **分页静默截断。** `_fetch_clist_all_pages` 在后续页失败时 `break` 并返回已取到的部分，调用方
   拿到的是一个看起来正常、实际残缺的全市场——选股会在少了若干只票的池子里排序而毫不知情。

本模块不重写取数，而是把同样的源、同样的解析函数放进 `run_with_contract` 里跑：一个总预算贯穿所有
源，每个源之前查取消与 deadline，socket 超时按剩余预算收紧，失败按类别归档，分页带回完整度。返回的
是 `TransportOutcome` —— 失败的 envelope 结构上不带 data，因此"零伪造回退"由类型保证而非靠自觉。
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from domain.models import DailyBar, FundFlow, MarketSnapshot, Quote, StockSymbol
from ports import (
    Attempt,
    CancelToken,
    Completeness,
    Deadline,
    ErrorClass,
    ManualCancel,
    TransportError,
    TransportOutcome,
    classify_http_status,
    run_with_contract,
)

from .data_provider import (
    BROWSER_USER_AGENT,
    CLIST_HOSTS,
    CLIST_URL,
    FUND_FLOW_HOSTS,
    FUND_FLOW_URL,
    HISTORY_URL,
    QUOTE_URL,
    SINA_HISTORY_URL,
    SINA_QUOTE_URL,
    TENCENT_FQ_HISTORY_URL,
    TENCENT_HISTORY_URL,
    MarketDataError,
    _clist_total,
    parse_clist_payload,
    parse_fund_flow_payload,
    parse_history_payload,
    parse_quote_payload,
    parse_sina_history_payload,
    parse_sina_quote_payload,
    parse_tencent_history_payload,
)

# 单次请求的超时上界。实际用的是它与 deadline 剩余预算的较小者——总预算收紧时，单次请求也得跟着收紧，
# 否则最后一个源可以独自把预算耗光还超出去。
DEFAULT_REQUEST_TIMEOUT = 8.0
DEFAULT_BUDGET_SECONDS = 20.0
_MIN_TIMEOUT = 0.05

_NEVER_CANCELLED = ManualCancel()

# 注意 encoding 必须一路传到 opener：新浪的两个源返回 gb18030，用 utf-8 解会把中文名称解成乱码。
type Opener = Callable[[urllib.request.Request, float, str | None], str]


def classify_exception(exc: BaseException) -> ErrorClass:
    """把底层异常归进 OBSERVABILITY.md 的类别。

    分界线是"换个源还有没有希望"：连不上/被拒/超时是 network（值得换源），而响应拿到了但内容不满足
    契约（截断的 JSON、字段漂移）是 parse——换源不会让同一份坏内容变好，重试只是浪费预算。
    """
    if isinstance(exc, urllib.error.HTTPError):
        return classify_http_status(exc.code)
    if isinstance(exc, json.JSONDecodeError):
        return "parse"
    if isinstance(exc, ssl.SSLError | ssl.CertificateError):
        return "network"
    if isinstance(exc, urllib.error.URLError):
        # URLError 是个信封：DNS 解析失败、TLS 握手失败、超时都裹在 reason 里。
        return "parse" if isinstance(exc.reason, json.JSONDecodeError) else "network"
    if isinstance(exc, TimeoutError | socket.timeout | ConnectionError):
        return "network"
    if isinstance(exc, http.client.IncompleteRead | http.client.RemoteDisconnected):
        return "network"
    if isinstance(exc, MarketDataError | ValueError | KeyError | TypeError):
        return "parse"
    if isinstance(exc, OSError):
        return "network"
    return "unknown"


class BoundedUrllibProvider:
    """把 urllib 取数包进 port 合同。每个 fetch_* 返回 envelope，不抛异常也不返回半真数据。"""

    def __init__(
        self,
        *,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        budget_seconds: float = DEFAULT_BUDGET_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        opener: Opener | None = None,
    ) -> None:
        self.request_timeout = request_timeout
        self.budget_seconds = budget_seconds
        self._clock = clock
        # 注入点：测试用它把整个矩阵（429/5xx/DNS/TLS/超时/截断/字段漂移）离线跑完，不碰真网络。
        self._opener = opener or _urlopen

    # --- 对外：四个取数 port ---

    def fetch_quote(
        self,
        symbol: StockSymbol,
        *,
        deadline: Deadline | None = None,
        cancel_token: CancelToken = _NEVER_CANCELLED,
    ) -> TransportOutcome[Quote]:
        budget = self._deadline(deadline)
        attempts: list[Attempt[Quote]] = [
            _guarded(
                "eastmoney",
                lambda: parse_quote_payload(
                    symbol, self._get(QUOTE_URL.format(secid=symbol.secid), budget)
                ),
            ),
            _guarded(
                "sina",
                lambda: parse_sina_quote_payload(
                    symbol,
                    self._get(
                        SINA_QUOTE_URL.format(symbol=symbol.normalized),
                        budget,
                        headers={"Referer": "https://finance.sina.com.cn/"},
                        encoding="gb18030",
                    ),
                ),
            ),
        ]
        return run_with_contract(attempts, deadline=budget, cancel_token=cancel_token)

    def fetch_history(
        self,
        symbol: StockSymbol,
        limit: int = 120,
        *,
        deadline: Deadline | None = None,
        cancel_token: CancelToken = _NEVER_CANCELLED,
    ) -> TransportOutcome[list[DailyBar]]:
        budget = self._deadline(deadline)
        limit = max(1, int(limit))

        def eastmoney() -> list[DailyBar]:
            payload = self._get(HISTORY_URL.format(secid=symbol.secid, limit=limit), budget)
            return _require_rows(parse_history_payload(payload), "东方财富历史日线为空")

        def sina() -> list[DailyBar]:
            payload = self._get(
                SINA_HISTORY_URL.format(symbol=symbol.normalized, limit=limit),
                budget,
                headers={"Referer": "https://finance.sina.com.cn/"},
                encoding="gb18030",
            )
            return _require_rows(parse_sina_history_payload(payload), "新浪历史日线为空")

        def tencent(url_template: str) -> Callable[[], list[DailyBar]]:
            def call() -> list[DailyBar]:
                payload = self._get(
                    url_template.format(symbol=symbol.normalized, limit=limit), budget
                )
                return _require_rows(
                    parse_tencent_history_payload(symbol, payload), "腾讯历史日线为空"
                )

            return call

        attempts: list[Attempt[list[DailyBar]]] = [
            _guarded("eastmoney", eastmoney),
            _guarded("sina", sina),
            _guarded("tencent_fq", tencent(TENCENT_FQ_HISTORY_URL)),
            _guarded("tencent", tencent(TENCENT_HISTORY_URL)),
        ]
        return run_with_contract(attempts, deadline=budget, cancel_token=cancel_token)

    def fetch_fund_flow(
        self,
        symbol: StockSymbol,
        limit: int = 6,
        *,
        deadline: Deadline | None = None,
        cancel_token: CancelToken = _NEVER_CANCELLED,
    ) -> TransportOutcome[FundFlow]:
        budget = self._deadline(deadline)
        limit = max(1, int(limit))

        def host_attempt(host: str) -> Callable[[], FundFlow]:
            def call() -> FundFlow:
                url = FUND_FLOW_URL.format(host=host, limit=limit, secid=symbol.secid)
                flow = parse_fund_flow_payload(self._get(url, budget), limit=limit)
                if flow is None:
                    # 同 _require_rows：空 = 这个主机没有，值得换下一个，不是内容不合契约。
                    raise TransportError("network", f"{host} 资金流为空")
                return flow

            return call

        attempts: list[Attempt[FundFlow]] = [
            _guarded(host, host_attempt(host)) for host in FUND_FLOW_HOSTS
        ]
        return run_with_contract(attempts, deadline=budget, cancel_token=cancel_token)

    def fetch_market_snapshot(
        self,
        page_size: int = 500,
        max_pages: int = 20,
        *,
        deadline: Deadline | None = None,
        cancel_token: CancelToken = _NEVER_CANCELLED,
    ) -> TransportOutcome[list[MarketSnapshot]]:
        """分页拉全市场，**带回完整度**。

        原实现在后续页失败时返回已取到的部分且不作声。这里把缺了哪几页、拿到多少 / 应有多少一起交出去，
        由调用方决定能不能用——一个残缺的全市场用于排序而不自知，比直接失败更危险。
        """
        budget = self._deadline(deadline)
        page_size = max(1, int(page_size))
        max_pages = max(1, int(max_pages))
        last_completeness = Completeness()
        tried: list[str] = []
        last_error: tuple[ErrorClass, str] = ("unknown", "没有可用的行情主机")

        for host in CLIST_HOSTS:
            if cancel_token.is_cancelled():
                return TransportOutcome.failed(
                    "network", "已取消", cancelled=True, attempts=tuple(tried)
                )
            if budget.expired():
                return TransportOutcome.failed(
                    "network", "操作超过总 deadline", attempts=tuple(tried)
                )
            tried.append(host)
            try:
                rows, last_completeness = self._paged_snapshot(
                    host, page_size, max_pages, budget, cancel_token
                )
            except TransportError as exc:
                last_error = (exc.error_class, exc.message)
                if exc.error_class != "network":
                    return TransportOutcome.failed(
                        exc.error_class, exc.message, attempts=tuple(tried)
                    )
                continue
            if rows:
                return TransportOutcome.ok(
                    rows, completeness=last_completeness, attempts=tuple(tried)
                )
            last_error = ("parse", f"{host} 返回为空")
        return TransportOutcome.failed(*last_error, attempts=tuple(tried))

    # --- 内部 ---

    def _paged_snapshot(
        self,
        host: str,
        page_size: int,
        max_pages: int,
        budget: Deadline,
        cancel_token: CancelToken,
    ) -> tuple[list[MarketSnapshot], Completeness]:
        collected: list[MarketSnapshot] = []
        seen: set[str] = set()
        total: int | None = None
        missing: list[int] = []

        for pn in range(1, max_pages + 1):
            if cancel_token.is_cancelled() or budget.expired():
                # 预算/取消在翻页途中到期：已取到的页照常返回，但缺页要记下来——这正是原实现丢掉的信息。
                missing.extend(range(pn, max_pages + 1))
                break
            try:
                payload = self._get(CLIST_URL.format(host=host, pn=pn, pz=page_size), budget)
            except TransportError:
                if pn == 1:
                    raise  # 第一页就失败：这个主机没拿到任何数据，交给上层换下一个主机
                missing.append(pn)
                break
            if total is None:
                total = _clist_total(payload)
            # 解析异常同样要变成分类过的 TransportError，否则会穿过 fetch_market_snapshot 的 except。
            rows = _parse_page(payload)
            if not rows:
                break
            for row in rows:
                if row.code in seen:
                    continue
                seen.add(row.code)
                collected.append(row)
            if total is not None and len(collected) >= total:
                break

        completeness = Completeness(
            expected=total,
            received=len(collected) if total is not None else None,
            missing_pages=tuple(missing),
        )
        return collected, completeness

    def _deadline(self, deadline: Deadline | None) -> Deadline:
        return deadline or Deadline.start(self.budget_seconds, clock=self._clock)

    def _get(
        self,
        url: str,
        deadline: Deadline,
        headers: dict[str, str] | None = None,
        encoding: str | None = None,
    ) -> str:
        """一次 HTTP GET。超时取"单次上界"与"剩余总预算"的较小者，失败一律翻译成分类过的 TransportError。"""
        remaining = deadline.remaining()
        if remaining <= 0:
            raise TransportError("network", "操作超过总 deadline")
        merged = {
            "User-Agent": BROWSER_USER_AGENT,
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if headers:
            merged.update(headers)
        request = urllib.request.Request(url, headers=merged)
        timeout = max(_MIN_TIMEOUT, min(self.request_timeout, remaining))
        try:
            return self._opener(request, timeout, encoding)
        except TransportError:
            raise
        except BaseException as exc:
            raise TransportError(classify_exception(exc), f"{type(exc).__name__}: {exc}") from exc


def _guarded[T](label: str, call: Callable[[], T]) -> Attempt[T]:
    """把一次尝试裹成"只会抛 TransportError"。

    必须裹在**解析之后**而不只是 HTTP 之后：`_get` 只覆盖请求，而 `parse_*` 会抛 MarketDataError /
    ValueError / KeyError。`run_with_contract` 只捕 TransportError，于是解析异常会穿过整个合同直接
    炸到调用方——envelope 的"绝不抛异常"承诺就此落空。这个包装是那道边界。
    """

    def attempt() -> T:
        try:
            return call()
        except TransportError:
            raise
        except BaseException as exc:
            raise TransportError(classify_exception(exc), f"{type(exc).__name__}: {exc}") from exc

    return (label, attempt)


def _parse_page(payload: str) -> list[MarketSnapshot]:
    """解析一页 clist，异常翻译成分类过的 TransportError（同 _guarded，只是用在翻页循环里）。"""
    try:
        return parse_clist_payload(payload)
    except BaseException as exc:
        raise TransportError(classify_exception(exc), f"{type(exc).__name__}: {exc}") from exc


def _require_rows(rows: list[DailyBar], message: str) -> list[DailyBar]:
    """空结果不是成功。

    归 network 而不是 parse，是因为分类在本合同里唯一的作用是"还该不该换源"：这个源没有数据，
    换一个很可能就有（原 provider 正是这么做的）。parse 表示的是"内容本身不合契约"，换源拿到的
    还是同样的坏内容——把空结果归进去会让备用源永远试不到。
    """
    if not rows:
        raise TransportError("network", message)
    return rows


def _urlopen(request: urllib.request.Request, timeout: float, encoding: str | None) -> str:
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        charset = encoding or response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")
