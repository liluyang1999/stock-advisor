from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from data.data_provider import MarketDataError
from domain.data_quality import DataQuality
from domain.engine import build_analysis_result, measure
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
from ports import Completeness

# 结构化日志（OBSERVABILITY.md）：编排层记任务/降级/失败，不记具体代码或原始 payload。
_log = get_logger("workflow")


class MarketDataProvider(Protocol):
    def fetch_quote(self, symbol: StockSymbol) -> Quote:
        raise NotImplementedError

    def fetch_history(self, symbol: StockSymbol) -> list[DailyBar]:
        raise NotImplementedError


class ScreeningProvider(MarketDataProvider, Protocol):
    def fetch_market_snapshot(
        self, page_size: int = 1000, max_pages: int = 12
    ) -> list[MarketSnapshot]:
        raise NotImplementedError

    # 可选：暴露最近一次全市场抓取的分页完整度（REQ-026）。不实现即视为完整（向后兼容），
    # 由 `_provider_completeness` 兜底，故旧 provider 与 FakeProvider 无需改动。


class CancelToken(Protocol):
    def is_set(self) -> bool:
        raise NotImplementedError


ProgressCallback = Callable[[int, int, Recommendation], None]


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
    fetched_at = datetime.now(UTC)
    try:
        quote = provider.fetch_quote(symbol)
    except MarketDataError as exc:
        # 实时行情取不到：返回不可分析（error，非伪造零价）——REQ-024 零伪造。
        _log.warning(
            "个股实时行情获取失败",
            extra=task_extra(
                operation="analyze_symbol.quote",
                error_class="network",
                degraded=True,
                outcome="unavailable",
            ),
        )
        return AnalysisOutcome(symbol=symbol, error=str(exc), quality=DataQuality(level="invalid"))
    except ValueError as exc:
        _log.warning(
            "个股实时行情不满足契约",
            extra=task_extra(
                operation="analyze_symbol.quote",
                error_class="parse",
                degraded=True,
                outcome="malformed",
            ),
        )
        return AnalysisOutcome(symbol=symbol, error=str(exc), quality=DataQuality(level="invalid"))
    except Exception as exc:
        _log.error(
            "个股实时行情意外失败",
            extra=task_extra(
                operation="analyze_symbol.quote",
                error_class="unknown",
                degraded=True,
                outcome="error",
            ),
            exc_info=True,
        )
        return AnalysisOutcome(
            symbol=symbol, error=f"实时行情获取失败：{exc}", quality=DataQuality(level="invalid")
        )

    degraded = False
    history_error = ""
    try:
        history = provider.fetch_history(symbol)
    except (MarketDataError, ValueError) as exc:
        # 历史取不到不致命：降级为实时价格做保守判断（真实降级，非伪造历史）——degraded=True。
        _log.warning(
            "历史日线取不到，降级为实时价格保守判断",
            extra=task_extra(
                operation="analyze_symbol.history",
                error_class="network" if isinstance(exc, MarketDataError) else "parse",
                degraded=True,
                outcome="degraded_history",
            ),
        )
        degraded = True
        history = []
        history_error = (
            "历史数据暂时取不到，系统已改用实时价格做保守判断。建议稍后重试或降低投入比例。"
        )
    except Exception:
        _log.error(
            "历史日线意外失败，降级为实时价格保守判断",
            extra=task_extra(
                operation="analyze_symbol.history",
                error_class="unknown",
                degraded=True,
                outcome="degraded_history",
            ),
            exc_info=True,
        )
        degraded = True
        history = []
        history_error = (
            "历史数据暂时取不到，系统已改用实时价格做保守判断。建议稍后重试或降低投入比例。"
        )

    try:
        m = measure(quote, history)
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
        fetched_at=fetched_at,
        degradations=(history_error,) if history_error else (),
    )
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

    try:
        snapshots = provider.fetch_market_snapshot()
    except (MarketDataError, ValueError) as exc:
        # 全市场拉取失败：明确报错，不伪造结果（REQ-024）。首段失败即整轮失败（无部分可用数据）。
        _log.warning(
            "全市场快照获取失败",
            extra=task_extra(
                operation="screen.snapshot",
                error_class="network" if isinstance(exc, MarketDataError) else "parse",
                degraded=True,
                outcome="unavailable",
            ),
        )
        return ScreenReport(total=0, matched=0, recommendations=[], error=str(exc))
    except Exception as exc:  # noqa: BLE001 - 兜底为可读错误，避免线程里裸异常
        _log.error(
            "全市场快照意外失败",
            extra=task_extra(
                operation="screen.snapshot", error_class="unknown", degraded=True, outcome="error"
            ),
            exc_info=True,
        )
        return ScreenReport(
            total=0, matched=0, recommendations=[], error=f"全市场行情获取失败：{exc}"
        )

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
            )
        recommendation = Recommendation(
            rank=index,
            snapshot=snapshot,
            screen_score=round(score, 2),
            board=board_of(snapshot),
        )
        if deep:
            recommendation = _deep_analyze(recommendation, provider, level)
        recommendations.append(recommendation)
        if progress_cb is not None:
            progress_cb(index, len(top), recommendation)

    return ScreenReport(
        total=len(snapshots),
        matched=len(filtered),
        recommendations=recommendations,
        completeness=_provider_completeness(provider),
    )


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
