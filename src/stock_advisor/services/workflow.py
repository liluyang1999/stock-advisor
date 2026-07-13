from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from typing import Callable, Protocol

from ..data.data_provider import MarketDataError
from ..domain.engine import build_analysis_result, measure
from ..domain.models import (
    AnalysisResult,
    DailyBar,
    FilterCriteria,
    MarketSnapshot,
    Measurement,
    Quote,
    Recommendation,
    STANDARD_LEVEL,
    StockSymbol,
)
from ..domain.policy import decide
from ..domain.screener import apply_filters, board_of, rank
from ..domain.symbols import symbol_from_market


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

    @property
    def ok(self) -> bool:
        return self.result is not None and not self.error


def analyze_symbol(
    symbol: StockSymbol, provider: MarketDataProvider, level: int = STANDARD_LEVEL
) -> AnalysisOutcome:
    try:
        quote = provider.fetch_quote(symbol)
    except (MarketDataError, ValueError) as exc:
        return AnalysisOutcome(symbol=symbol, error=str(exc))
    except Exception as exc:
        return AnalysisOutcome(symbol=symbol, error=f"实时行情获取失败：{exc}")

    degraded = False
    try:
        history = provider.fetch_history(symbol)
    except MarketDataError, ValueError:
        degraded = True
        history = []
        history_error = (
            "历史数据暂时取不到，系统已改用实时价格做保守判断。建议稍后重试或降低投入比例。"
        )
    except Exception:
        degraded = True
        history = []
        history_error = (
            "历史数据暂时取不到，系统已改用实时价格做保守判断。建议稍后重试或降低投入比例。"
        )
    else:
        history_error = ""

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
    return AnalysisOutcome(
        symbol=symbol, result=result, measurement=m, history=history, degraded=degraded
    )


@dataclass(frozen=True)
class ScreenReport:
    total: int  # 全市场扫描数量
    matched: int  # 通过筛选数量
    recommendations: list[Recommendation] = field(default_factory=list)
    error: str = ""
    cancelled: bool = False

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
        return ScreenReport(total=0, matched=0, recommendations=[], error=str(exc))
    except Exception as exc:  # noqa: BLE001 - 兜底为可读错误，避免线程里裸异常
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
        total=len(snapshots), matched=len(filtered), recommendations=recommendations
    )


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
