from __future__ import annotations

import math
from statistics import mean

from .engine import clean_history, measure
from .models import BacktestReport, BacktestStat, DailyBar, Quote, StockSymbol, STANDARD_LEVEL
from .policy import decide


# 回测构造伪行情时不依赖具体证券代码（measure 不读 symbol），用占位 symbol 满足类型。
_PLACEHOLDER_SYMBOL = StockSymbol(
    raw="000000", code="000000", exchange="SZ", prefix="sz", secid="0.000000"
)


def quote_from_bar(bar: DailyBar, prev: DailyBar | None) -> Quote:
    prev_close = prev.close if prev else bar.open
    change = (bar.close - prev_close) / prev_close * 100 if prev_close else 0.0
    return Quote(
        symbol=_PLACEHOLDER_SYMBOL,
        name="",
        last=bar.close,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        previous_close=prev_close,
        volume=bar.volume,
        amount=bar.amount,
        turnover_rate=bar.turnover_rate,
        change_pct=change,
    )


def backtest_signals(
    history: list[DailyBar],
    level: int = STANDARD_LEVEL,
    horizon: int = 5,
    warmup: int = 30,
    cost_pct: float = 0.13,
) -> BacktestReport:
    """同股历史信号事后复盘：逐日只用当日及之前数据生成信号，度量未来 horizon 日收益。

    无未来泄漏：第 t 日信号只看 history[:t] + 第 t 根；未来收益仅作度量、不作输入。
    """
    try:
        horizon = int(horizon)
        warmup = int(warmup)
        cost_pct = float(cost_pct)
    except TypeError, ValueError, OverflowError:
        return BacktestReport(
            level=level,
            horizon=0,
            sample_size=0,
            buy_hold_return=0.0,
            note="参数无效",
            ok=False,
            message="回测参数无效：持有天数、预热样本和成本必须是数字。",
        )
    if horizon <= 0 or warmup <= 0 or not math.isfinite(cost_pct) or cost_pct < 0:
        return BacktestReport(
            level=level,
            horizon=max(0, horizon),
            sample_size=0,
            buy_hold_return=0.0,
            note="参数无效",
            ok=False,
            message="回测参数无效：持有天数和预热样本需大于0，成本不能为负。",
        )
    history = clean_history(history)
    n = len(history)
    if n < warmup + horizon + 1:
        return BacktestReport(
            level=level,
            horizon=horizon,
            sample_size=0,
            buy_hold_return=0.0,
            note="样本不足",
            ok=False,
            message="历史样本不足，暂不回测（需要更多交易日）。",
        )
    rows: dict[str, list[float]] = {"BUY": [], "SELL": [], "HOLD": []}
    gross_all: list[float] = []
    for t in range(warmup, n - horizon):
        as_of = history[: t + 1]
        quote = quote_from_bar(history[t], history[t - 1] if t > 0 else None)
        action = decide(measure(quote, as_of), level).action
        gross = (history[t + horizon].close - history[t].close) / history[t].close * 100
        rows[action].append(gross - cost_pct)
        gross_all.append(gross)

    stats: dict[str, BacktestStat] = {}
    for action, vals in rows.items():
        if not vals:
            continue
        if action == "SELL":
            wins = sum(1 for v in vals if v < 0)  # 卖出信号「对」= 之后下跌
        else:
            wins = sum(1 for v in vals if v > 0)
        stats[action] = BacktestStat(
            action=action,
            count=len(vals),
            win_rate=round(wins / len(vals), 4),
            avg_return=round(mean(vals), 4),
        )
    return BacktestReport(
        level=level,
        horizon=horizon,
        sample_size=sum(len(v) for v in rows.values()),
        buy_hold_return=round(mean(gross_all), 4) if gross_all else 0.0,
        note=f"近{n}日 · 持有{horizon}日 · 单边成本{cost_pct}% · 仅用当日及之前数据，不预示未来",
        stats=stats,
    )
