"""离线样例行情、分析与推荐构造——纯函数，供自测/演示复用。"""

from __future__ import annotations

from ..domain.engine import analyze_stock, measure
from ..domain.models import (
    AnalysisResult,
    DailyBar,
    MarketSnapshot,
    Measurement,
    Quote,
    Recommendation,
)
from ..domain.symbols import normalize_symbol


def _sample_quote_history() -> tuple[Quote, list[DailyBar]]:
    history: list[DailyBar] = []
    price = 20.0
    for day in range(80):
        close = price + 0.08
        history.append(
            DailyBar(
                date=f"2026-05-{day + 1:02d}",
                open=price,
                close=close,
                high=close + 0.06,
                low=price - 0.04,
                volume=120000 + day * 300,
                amount=(120000 + day * 300) * close,
                pct_change=(close - price) / price * 100,
                turnover_rate=1.2,
            )
        )
        price = close
    quote = Quote(
        symbol=normalize_symbol("600519"),
        name="离线样例",
        last=26.6,
        open=26.3,
        high=26.8,
        low=26.1,
        previous_close=26.2,
        volume=210000,
        amount=210000 * 26.6,
        turnover_rate=2.1,
        change_pct=1.53,
        timestamp="self-test",
    )
    return quote, history


def make_sample_analysis() -> AnalysisResult:
    quote, history = _sample_quote_history()
    return analyze_stock(quote, history)


def make_sample_measurement() -> Measurement:
    quote, history = _sample_quote_history()
    return measure(quote, history)


def make_sample_history() -> list[DailyBar]:
    return _sample_quote_history()[1]


def make_sample_recommendation(deep: bool = True) -> Recommendation:
    snapshot = MarketSnapshot(
        code="600519",
        market_id="1",
        name="离线样例",
        price=26.6,
        change_pct=1.53,
        change=0.4,
        volume=210000,
        amount=210000 * 26.6,
        amplitude=2.6,
        turnover_rate=2.1,
        pe_ttm=24.0,
        volume_ratio=1.4,
        total_cap=3.0e12,
        float_cap=3.0e12,
        speed=0.3,
        pb=8.0,
        change_60d=12.0,
        change_ytd=18.0,
    )
    result = make_sample_analysis() if deep else None
    return Recommendation(
        rank=1, snapshot=snapshot, screen_score=42.0, board="沪市主板", result=result
    )
