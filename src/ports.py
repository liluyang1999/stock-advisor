"""网络传输的 port / envelope 基础合同（REQ-025 / REQ-026 / ADR-0003 / WI-009）。

ADR-0003 定死了网络边界：终态是 `NetworkWorker(QObject)` + 专用 `QThread` + `QNetworkAccessManager`，
迁移期是把现有同步 urllib provider 用有界 `QThreadPool` 包装；**两条路径实现同一个 port/envelope**，
都使用总 deadline 与协作取消。本模块就是那个 port——**框架无关、纯 stdlib**（不 import PySide6 也不
import urllib），因此两种传输都能实现它，且合同逻辑可离线确定性测试。

三个不可绕过的性质：
1. **错误分类**：每次失败归入 `OBSERVABILITY.md` 的 7 类之一（此处只用得到 network/parse/validation）。
2. **总 deadline**：一个 deadline 覆盖所有重试与备用源，不允许每个源重新获得完整预算（ADR-0003）。
3. **零伪造回退**：失败的 envelope **结构上不携带数据**——`TransportOutcome.failed(...)` 没有 data 字段，
   调用方拿不到假数据（REQ-024 / DoD 的 "zero fabricated fallbacks"）。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

# OBSERVABILITY.md 的 7 类错误（唯一权威）。传输层实际只产生前三类；其余供归类完整性。
ErrorClass = Literal["network", "parse", "validation", "persistence", "gui", "packaging", "unknown"]

# 可对同一 port 换源重试的分类：只有瞬时网络类可换下一个备用源；parse（内容不满足契约）与
# validation（输入非法）换源也没用，ADR-0003 明确"4xx 参数/权限/解析合同错误不盲重试"。
_RETRYABLE: frozenset[ErrorClass] = frozenset({"network"})


class TransportError(Exception):
    """携带显式 error_class 的传输失败。具体传输（urllib 桥 / QNAM worker）在捕获各自的
    底层异常后，用正确的类别构造它，从而把"如何归类"这一权威留在本合同里而非散落各处。"""

    def __init__(self, error_class: ErrorClass, message: str) -> None:
        super().__init__(message)
        self.error_class: ErrorClass = error_class
        self.message = message


def classify_http_status(status: int) -> ErrorClass:
    """任何 HTTP 状态码都归 network（OBSERVABILITY：network 含"HTTP 状态"）。

    分类不区分 2xx/4xx/5xx——凡是"拿到了 HTTP 状态但不是成功内容"都属连接/协议层面的 network；
    响应内容本身不满足契约（截断、字段漂移等）由调用方以 parse 抛出，不走这里。
    """

    return "network"


class CancelToken(Protocol):
    """协作取消：传输在每个可中断点查询它。取消是"结果状态"，与 error_class 正交。"""

    def is_cancelled(self) -> bool: ...


class ManualCancel:
    """最简协作取消原语，供 controller/测试驱动。

    同时满足两个既有取消协议：传输/批量编排查询 `is_cancelled()`，而全市场筛选编排
    （`services.workflow.screen_and_recommend`）沿用 `threading.Event` 风格的 `is_set()`。
    两者同义，故一个原语可横跨传输/批量/筛选，Qt 控制器无须为不同编排各带一种取消对象。
    """

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def is_set(self) -> bool:
        """`is_cancelled()` 的别名，匹配 screener 编排的 `threading.Event` 风格取消协议。"""
        return self._cancelled


_NEVER_CANCELLED = ManualCancel()


@dataclass(frozen=True)
class Deadline:
    """一个总预算，覆盖一次操作的所有重试与备用源。用注入的单调时钟计时以便测试确定性。"""

    budget_seconds: float
    started_at: float
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def start(cls, budget_seconds: float, clock: Callable[[], float] = time.monotonic) -> Deadline:
        return cls(budget_seconds=budget_seconds, started_at=clock(), clock=clock)

    def remaining(self) -> float:
        return self.budget_seconds - (self.clock() - self.started_at)

    def expired(self) -> bool:
        return self.remaining() <= 0


@dataclass(frozen=True)
class Completeness:
    """分页/样本完整度（REQ-026）。默认是"完整、无缺"，附加它不改变既有语义。"""

    expected: int | None = None
    received: int | None = None
    missing_pages: tuple[int, ...] = ()

    @property
    def is_complete(self) -> bool:
        if self.missing_pages:
            return False
        if self.expected is None or self.received is None:
            return True
        return self.received >= self.expected


@dataclass(frozen=True)
class TransportOutcome[T]:
    """一次传输的结果 envelope。**成功才带 data；失败结构上不带 data**——这就是"零伪造回退"的
    机器保证：任何失败路径都无法把假数据交给调用方。用 `ok(...)` / `failed(...)` 构造，别直接实例化。"""

    succeeded: bool
    data: T | None = None
    completeness: Completeness = field(default_factory=Completeness)
    error_class: ErrorClass | None = None
    message: str = ""
    cancelled: bool = False
    attempts: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    """走过的源/尝试标签，供可观测性追溯（哪些源试过、以何顺序）。"""

    @classmethod
    def ok(
        cls,
        data: T,
        completeness: Completeness | None = None,
        attempts: tuple[str, ...] = (),
        notes: tuple[str, ...] = (),
    ) -> TransportOutcome[T]:
        return cls(
            succeeded=True,
            data=data,
            completeness=completeness or Completeness(),
            attempts=attempts,
            notes=notes,
        )

    @classmethod
    def failed(
        cls,
        error_class: ErrorClass,
        message: str,
        *,
        cancelled: bool = False,
        attempts: tuple[str, ...] = (),
        completeness: Completeness | None = None,
    ) -> TransportOutcome[T]:
        return cls(
            succeeded=False,
            completeness=completeness or Completeness(),
            error_class=error_class,
            message=message,
            cancelled=cancelled,
            attempts=attempts,
        )


# 一次尝试：给个标签和一个零参可调用；成功返回数据，失败抛 TransportError。
type Attempt[T] = tuple[str, Callable[[], T]]


def run_with_contract[T](
    attempts: Sequence[Attempt[T]] | Iterable[Attempt[T]],
    *,
    deadline: Deadline,
    cancel_token: CancelToken = _NEVER_CANCELLED,
    completeness: Completeness | None = None,
) -> TransportOutcome[T]:
    """按合同依次跑备用源链：每个可中断点先查取消、再查 deadline，成功即返回，全失败则返回带
    分类的失败 envelope（零伪造）。这精确对应现有 provider 的多源回退循环，只是在源与源之间加了
    取消与总 deadline 检查——正是迁移桥要满足的合同。

    - 取消优先于一切：任何尝试前若已取消，立即返回 cancelled 失败。
    - deadline 覆盖所有源：预算耗尽即停，归 network（超时属 network）。
    - 只有 network 类失败才继续换下一个源；parse/validation 失败换源无意义，直接返回该分类。
    """

    tried: list[str] = []
    last_error_class: ErrorClass = "unknown"
    last_message = "no attempts supplied"

    for label, call in attempts:
        if cancel_token.is_cancelled():
            return TransportOutcome.failed(
                "network", "已取消", cancelled=True, attempts=tuple(tried)
            )
        if deadline.expired():
            return TransportOutcome.failed("network", "操作超过总 deadline", attempts=tuple(tried))
        tried.append(label)
        try:
            data = call()
        except TransportError as exc:
            if cancel_token.is_cancelled():
                return TransportOutcome.failed(
                    "network", "已取消", cancelled=True, attempts=tuple(tried)
                )
            if deadline.expired():
                return TransportOutcome.failed(
                    "network", "操作超过总 deadline", attempts=tuple(tried)
                )
            last_error_class, last_message = exc.error_class, exc.message
            if exc.error_class not in _RETRYABLE:
                # 内容契约/输入错误：换源也没用，立即返回该分类（不伪造数据）。
                return TransportOutcome.failed(exc.error_class, exc.message, attempts=tuple(tried))
            continue  # 瞬时网络错误：尝试下一个备用源
        else:
            if cancel_token.is_cancelled():
                return TransportOutcome.failed(
                    "network", "已取消", cancelled=True, attempts=tuple(tried)
                )
            if deadline.expired():
                return TransportOutcome.failed(
                    "network", "操作超过总 deadline", attempts=tuple(tried)
                )
            return TransportOutcome.ok(data, completeness=completeness, attempts=tuple(tried))

    return TransportOutcome.failed(last_error_class, last_message, attempts=tuple(tried))
