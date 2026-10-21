from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from data.data_provider import MarketDataError
from domain.data_quality import DataProvenance, DataQuality
from domain.engine import build_analysis_result, clean_history, measure
from domain.models import (
    STANDARD_LEVEL,
    AnalysisResult,
    DailyBar,
    FilterCriteria,
    MarketSnapshot,
    Measurement,
    Quote,
    Recommendation,
    StockSymbol,
)
from domain.policy import decide
from domain.screener import apply_filters, board_of, rank
from domain.symbols import symbol_from_market
from observability import get_logger, task_extra
from ports import Completeness, TransportOutcome

# 结构化日志（OBSERVABILITY.md）：编排层记任务/降级/失败，不记具体代码或原始 payload。
_log = get_logger("workflow")


class MarketDataProvider(Protocol):
    def fetch_quote(self, symbol: StockSymbol) -> Quote:
        raise NotImplementedError

    def fetch_history(self, symbol: StockSymbol) -> list[DailyBar]:
        raise NotImplementedError


class ScreeningProvider(MarketDataProvider, Protocol):
    def fetch_market_snapshot(
        self, page_size: int = 100, max_pages: int = 100
    ) -> list[MarketSnapshot]:
        raise NotImplementedError

    # 可选：暴露最近一次全市场抓取的分页完整度（REQ-026）。不实现即视为完整（向后兼容），
    # 由 `_provider_completeness` 兜底，故旧 provider 与 FakeProvider 无需改动。


class CancelToken(Protocol):
    def is_set(self) -> bool:
        raise NotImplementedError


ProgressCallback = Callable[[int, int, Recommendation], None]


def _fetch_outcome(provider: object, name: str, *args: object) -> TransportOutcome:
    """把一次取数收敛成 envelope，让编排层只有**一条**路径（WI-033）。

    provider 提供 `<name>_outcome` 就直接用它：传输层自己算出的 `error_class`（network/parse/
    validation）与 `cancelled` 由此原样抵达编排层。此前这里只看得见异常，分类只能靠
    `isinstance(exc, MarketDataError)` 二选一地猜，取消更是与失败无从区分。

    老式 provider 与测试替身仍然抛异常，这里按同一口径包成等价的失败信封——因此**不必改
    `MarketDataProvider` Protocol，也不必动任何既有 provider**，两边共用同一段下游逻辑。
    """

    envelope = getattr(provider, f"{name}_outcome", None)
    if callable(envelope):
        outcome = envelope(*args)
        if isinstance(outcome, TransportOutcome):
            return outcome
    try:
        return TransportOutcome.ok(getattr(provider, name)(*args))
    except MarketDataError as exc:
        return TransportOutcome.failed("network", str(exc))
    except ValueError as exc:
        return TransportOutcome.failed("parse", str(exc))
    except Exception as exc:  # noqa: BLE001 - 兜底为可读失败信封，避免后台线程里裸异常
        return TransportOutcome.failed("unknown", str(exc))


@dataclass(frozen=True)
class AnalysisOutcome:
    symbol: StockSymbol
    result: AnalysisResult | None = None
    measurement: Measurement | None = None
    history: list[DailyBar] = field(default_factory=list)
    error: str = ""
    degraded: bool = False
    quality: DataQuality = field(default_factory=DataQuality)
    """数据质量信封（REQ-023/WI-007）：来源/获取时间/完整度/新鲜度/降级状态。`degraded` 这个
    裸 bool 保留作向后兼容；`quality` 是它的正名版——带等级、可见降级原因与获取时间。"""

    @property
    def ok(self) -> bool:
        return self.result is not None and not self.error


def analyze_symbol(
    symbol: StockSymbol, provider: MarketDataProvider, level: int = STANDARD_LEVEL
) -> AnalysisOutcome:
    quote_outcome = _fetch_outcome(provider, "fetch_quote", symbol)
    quote_at = datetime.now(UTC)
    if not quote_outcome.succeeded or quote_outcome.data is None:
        # 实时行情取不到：返回不可分析（error，非伪造零价）——REQ-024 零伪造。
        # 分类与「是否被取消」都取自 envelope，不再由异常类型反推。
        error_class = quote_outcome.error_class or "unknown"
        _log.warning(
            "个股实时行情获取失败",
            extra=task_extra(
                operation="analyze_symbol.quote",
                error_class=error_class,
                degraded=True,
                outcome="cancelled" if quote_outcome.cancelled else "unavailable",
            ),
        )
        # unknown 保留前缀（老式 provider 的兜底路径的既有文案），其余直接用传输层给的原因。
        message = quote_outcome.message
        if error_class == "unknown":
            message = f"实时行情获取失败：{message}"
        return AnalysisOutcome(symbol=symbol, error=message, quality=DataQuality(level="invalid"))
    quote = quote_outcome.data

    degraded = False
    history_error = ""
    history: list[DailyBar] = []
    history_outcome = _fetch_outcome(provider, "fetch_history", symbol)
    history_at = datetime.now(UTC)
    if history_outcome.cancelled:
        # 取消应终止本次分析，不能按取数故障降级后继续生成、缓存新的结论。
        _log.info(
            "历史日线请求已取消",
            extra=task_extra(
                operation="analyze_symbol.history", outcome="cancelled", cancelled=True
            ),
        )
        return AnalysisOutcome(
            symbol=symbol,
            error=history_outcome.message or "历史日线请求已取消",
            quality=DataQuality(level="invalid"),
        )
    if history_outcome.succeeded:
        # 注意这里**不**做 `data is not None` 的兜底：取数成功却给回 None 是 provider 违约，
        # 交给下面的 `measure` 抛出来变成"分析计算失败"，而不是静默降级把违约盖掉
        # （既有契约 test_malformed_history_returns_failure_outcome_instead_of_raising）。
        history = history_outcome.data  # type: ignore[assignment] - 故意放行违约的 None
    else:
        # 历史取不到不致命：降级为实时价格做保守判断（真实降级，非伪造历史）——degraded=True。
        _log.warning(
            "历史日线取不到，降级为实时价格保守判断",
            extra=task_extra(
                operation="analyze_symbol.history",
                error_class=history_outcome.error_class or "unknown",
                degraded=True,
                outcome="degraded_history",
            ),
        )
        degraded = True
        history = []
        history_error = (
            "历史数据暂时取不到，系统已改用实时价格做保守判断。建议稍后重试或降低投入比例。"
        )

    try:
        original_history = history
        history = clean_history(history)
        if len(history) < 30:
            degraded = True
            history_error = history_error or "历史有效样本少于30个交易日，当前结果已降级。"
        m = measure(quote, history)
        if history != original_history:
            m = replace(m, risks=["历史日线已校验排序并清理重复或无效记录。", *m.risks])
        if history_outcome.notes:
            m = replace(m, risks=[*history_outcome.notes, *m.risks])
        if history_error:
            # 注入降级提示到测量层，改档重判时也会随结论带出。
            m = replace(m, risks=[history_error, *m.risks])
        result = build_analysis_result(m, decide(m, level))
    except ValueError as exc:
        return AnalysisOutcome(symbol=symbol, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - provider 数据结构异常应返回可展示错误，避免后台线程裸异常
        return AnalysisOutcome(symbol=symbol, error=f"分析计算失败：{exc}")
    quality = DataQuality(
        level="degraded_history" if degraded else "complete",
        fetched_at=quote_at,
        provenance=tuple(
            DataProvenance(
                source=o.attempts[-1],
                endpoint=name,
                fallback_rank=len(o.attempts) - 1,
                fetched_at=acquired,
                adjustment=(
                    "前复权请求" if o.attempts[-1] in {"eastmoney", "tencent_fq"} else "不复权"
                )
                if name == "history"
                else "",
            )
            for name, o, acquired in (
                ("quote", quote_outcome, quote_at),
                ("history", history_outcome, history_at),
            )
            if o.succeeded and o.attempts
        ),
        degradations=history_outcome.notes + ((history_error,) if history_error else ()),
    )
    if quality.provenance:
        labels = {"eastmoney": "东方财富", "sina": "新浪", "tencent_fq": "腾讯", "tencent": "腾讯"}
        notes = [
            f"{'行情' if p.endpoint == 'quote' else '日线'}：{labels.get(p.source, p.source)}"
            + (f"（{p.adjustment}）" if p.adjustment else "")
            + (f"，备用源第{p.fallback_rank}位" if p.fallback_rank else "")
            for p in quality.provenance
        ]
        note = (
            "数据来源："
            + "；".join(notes)
            + f"；行情获取时间 {quote_at.isoformat(timespec='seconds')}（UTC），不代表交易所报价时间；有效日线 {m.history_len} 条。"
        )
        note += " ".join(history_outcome.notes)
        m = replace(m, data_note=note)
        result = replace(result, data_note=note)
    return AnalysisOutcome(
        symbol=symbol,
        result=result,
        measurement=m,
        history=history,
        degraded=degraded,
        quality=quality,
    )


@dataclass(frozen=True)
class ScreenReport:
    total: int  # 全市场扫描数量
    matched: int  # 通过筛选数量
    recommendations: list[Recommendation] = field(default_factory=list)
    error: str = ""
    cancelled: bool = False
    completeness: Completeness = field(default_factory=Completeness)
    """市场分页完整度（REQ-026/WI-014）。默认"完整"；provider 报告分页不完整时为
    partial（`is_complete` 为 False），UI 据此提示"非全市场结果"（DATA_QUALITY 的 partial_market）。"""

    @property
    def ok(self) -> bool:
        return not self.error


def screen_and_recommend(
    provider: ScreeningProvider,
    criteria: FilterCriteria,
    objective: str,
    top_n: int = 20,
    deep: bool = True,
    cancel_event: CancelToken | None = None,
    progress_cb: ProgressCallback | None = None,
    level: int = STANDARD_LEVEL,
) -> ScreenReport:
    """拉全市场快照 → 按条件筛选 → 排序取 TopN →（可选）对 TopN 深度分析。

    单只深度分析失败不影响其他；首段全市场拉取失败则明确报错，不伪造结果。
    """
    top_limit = _top_limit(top_n)
    if top_limit is None:
        return ScreenReport(total=0, matched=0, recommendations=[], error="推荐数量参数无效")

    snapshot_outcome = _fetch_outcome(provider, "fetch_market_snapshot")
    if not snapshot_outcome.succeeded or snapshot_outcome.data is None:
        # 全市场拉取失败：明确报错，不伪造结果（REQ-024）。首段失败即整轮失败（无部分可用数据）。
        if snapshot_outcome.cancelled:
            # 取消不是失败：`ScreenReport.cancelled` 此前永远是 False，因为取消经异常传上来时
            # 与超时长得一模一样，界面只能笼统说"获取失败"。
            _log.info(
                "全市场快照已取消",
                extra=task_extra(
                    operation="screen.snapshot", error_class="network", outcome="cancelled"
                ),
            )
            return ScreenReport(total=0, matched=0, recommendations=[], cancelled=True)
        error_class = snapshot_outcome.error_class or "unknown"
        _log.warning(
            "全市场快照获取失败",
            extra=task_extra(
                operation="screen.snapshot",
                error_class=error_class,
                degraded=True,
                outcome="unavailable",
            ),
        )
        # unknown 保留前缀（老式 provider 兜底路径的既有文案），其余直接用传输层给的原因。
        message = snapshot_outcome.message
        if error_class == "unknown":
            message = f"全市场行情获取失败：{message}"
        return ScreenReport(total=0, matched=0, recommendations=[], error=message)
    snapshots = snapshot_outcome.data
    completeness = _completeness_of(provider, snapshot_outcome)

    filtered = apply_filters(snapshots, criteria)
    ranked = rank(filtered, objective)
    top = ranked[:top_limit]

    recommendations: list[Recommendation] = []
    for index, (score, snapshot) in enumerate(top, start=1):
        if cancel_event is not None and cancel_event.is_set():
            return ScreenReport(
                total=len(snapshots),
                matched=len(filtered),
                recommendations=recommendations,
                cancelled=True,
                completeness=completeness,
            )
        recommendation = Recommendation(
            rank=index,
            snapshot=snapshot,
            screen_score=round(score, 2),
            board=board_of(snapshot),
        )
        if deep:
            recommendation = _deep_analyze(recommendation, provider, level)
        if cancel_event is not None and cancel_event.is_set():
            return ScreenReport(
                total=len(snapshots),
                matched=len(filtered),
                recommendations=recommendations,
                cancelled=True,
                completeness=completeness,
            )
        recommendations.append(recommendation)
        if progress_cb is not None:
            progress_cb(index, len(top), recommendation)

    return ScreenReport(
        total=len(snapshots),
        matched=len(filtered),
        recommendations=recommendations,
        completeness=completeness,
        cancelled=cancel_event is not None and cancel_event.is_set(),
    )


def _completeness_of(provider: ScreeningProvider, outcome: TransportOutcome) -> Completeness:
    """完整度优先取 envelope 自带的那份——它就是传输层分页时算出来的，最权威。

    老式 provider 走 `_fetch_outcome` 的异常包装路径，其 envelope 只有默认完整度，故退回
    duck-typed 的 `market_completeness()` 取法（旧 provider 与 FakeProvider 因此行为不变）。
    """

    if callable(getattr(provider, "fetch_market_snapshot_outcome", None)):
        return outcome.completeness
    return _provider_completeness(provider)


def _provider_completeness(provider: ScreeningProvider) -> Completeness:
    """取 provider 的市场分页完整度；旧 provider 未实现则视为完整（向后兼容）。"""
    getter = getattr(provider, "market_completeness", None)
    if getter is None:
        return Completeness()
    try:
        result = getter()
    except Exception:  # noqa: BLE001 - 完整度是附加信息，取不到不应影响筛选结果
        return Completeness()
    return result if isinstance(result, Completeness) else Completeness()


def _top_limit(value: object) -> int | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return int(number)


def _deep_analyze(
    recommendation: Recommendation, provider: MarketDataProvider, level: int = STANDARD_LEVEL
) -> Recommendation:
    snapshot = recommendation.snapshot
    try:
        symbol = symbol_from_market(snapshot.code, snapshot.market_id)
    except ValueError as exc:
        return replace(recommendation, error=f"代码市场信息缺失：{exc}")
    outcome = analyze_symbol(symbol, provider, level)
    if outcome.ok and outcome.result is not None:
        return replace(recommendation, result=outcome.result, measurement=outcome.measurement)
    return replace(recommendation, error=outcome.error or "深度分析失败")
