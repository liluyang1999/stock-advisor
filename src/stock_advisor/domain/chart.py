from __future__ import annotations

import math
from statistics import mean

from .models import DailyBar


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError, OverflowError:
        return None
    return number if math.isfinite(number) else None


def _positive_finite_float(value: object) -> float | None:
    number = _finite_float(value)
    return number if number is not None and number > 0 else None


def _nonnegative_finite_float(value: object) -> float | None:
    number = _finite_float(value)
    return number if number is not None and number >= 0 else None


def index_to_x(i: int, n: int, left: float, right: float) -> float:
    """把第 i 根（共 n 根）映射到 [left, right] 的横坐标。"""
    if n <= 1:
        return (left + right) / 2
    return left + (right - left) * i / (n - 1)


def price_to_y(price: float, lo: float, hi: float, top: float, height: float) -> float:
    """价格映射到纵坐标（y 向下增长，故最高价在顶部 top，最低价在底部 top+height）。"""
    safe_top = _finite_float(top) or 0.0
    safe_height = _finite_float(height)
    if safe_height is None or safe_height < 0:
        safe_height = 0.0
    midpoint = safe_top + safe_height / 2

    safe_price = _finite_float(price)
    safe_lo = _finite_float(lo)
    safe_hi = _finite_float(hi)
    if safe_price is None or safe_lo is None or safe_hi is None or safe_hi <= safe_lo:
        return midpoint

    ratio = (safe_price - safe_lo) / (safe_hi - safe_lo)
    ratio = max(0.0, min(1.0, ratio))
    return safe_top + (1 - ratio) * safe_height


def moving_average_series(closes: list[float], window: int) -> list[float | None]:
    """逐点均线；不足 window 的前段记 None。"""
    if window <= 0:
        return [None] * len(closes)
    out: list[float | None] = []
    for i in range(len(closes)):
        if i < window - 1:
            out.append(None)
        else:
            window_values = [_finite_float(value) for value in closes[i - window + 1 : i + 1]]
            if any(value is None for value in window_values):
                out.append(None)
            else:
                out.append(mean(value for value in window_values if value is not None))
    return out


def price_bounds(bars: list[DailyBar]) -> tuple[float, float]:
    prices: list[float] = []
    for bar in bars:
        for value in (bar.open, bar.close, bar.high, bar.low):
            price = _positive_finite_float(value)
            if price is not None:
                prices.append(price)
    if not prices:
        return 0.0, 1.0
    return min(prices), max(prices)


def volume_heights(bars: list[DailyBar], max_height: float) -> list[float]:
    safe_height = _finite_float(max_height)
    if safe_height is None or safe_height <= 0:
        return [0.0] * len(bars)
    volumes = [_nonnegative_finite_float(bar.volume) or 0.0 for bar in bars]
    max_volume = max(volumes, default=0.0)
    if max_volume <= 0:
        return [0.0] * len(bars)
    return [volume / max_volume * safe_height for volume in volumes]


def nearest_index(x: float, layout: list[dict]) -> int:
    """hover：返回 x 最近的蜡烛下标；layout 为 candle_layout 结果。空则 -1。"""
    target = _finite_float(x)
    if target is None or not layout:
        return -1
    best = -1
    best_distance = math.inf
    for index, cell in enumerate(layout):
        cell_x = _finite_float(cell.get("x"))
        if cell_x is None:
            continue
        distance = abs(cell_x - target)
        if distance < best_distance:
            best_distance = distance
            best = index
    return best


def _fallback_price(lo: float, hi: float) -> float:
    if hi > lo:
        return (lo + hi) / 2
    if lo > 0:
        return lo
    return 0.5


def _candle_prices(bar: DailyBar, fallback: float) -> tuple[float, float, float, float]:
    raw_open = _positive_finite_float(bar.open)
    raw_close = _positive_finite_float(bar.close)
    raw_high = _positive_finite_float(bar.high)
    raw_low = _positive_finite_float(bar.low)

    open_price = raw_open if raw_open is not None else raw_close or fallback
    close_price = raw_close if raw_close is not None else open_price
    candidates = [open_price, close_price]
    if raw_high is not None:
        candidates.append(raw_high)
    if raw_low is not None:
        candidates.append(raw_low)
    high_price = max(candidates)
    low_price = min(candidates)
    return open_price, close_price, high_price, low_price


def candle_layout(
    bars: list[DailyBar], left: float, right: float, top: float, height: float
) -> list[dict]:
    """每根蜡烛的绘制坐标：x、影线上下端、实体上下沿、涨跌。"""
    n = len(bars)
    lo, hi = price_bounds(bars)
    fallback = _fallback_price(lo, hi)
    layout: list[dict] = []
    for i, bar in enumerate(bars):
        open_price, close_price, high_price, low_price = _candle_prices(bar, fallback)
        fallback = close_price
        layout.append(
            {
                "x": index_to_x(i, n, left, right),
                "up": close_price >= open_price,
                "wick_top": price_to_y(high_price, lo, hi, top, height),
                "wick_bottom": price_to_y(low_price, lo, hi, top, height),
                "body_top": price_to_y(max(open_price, close_price), lo, hi, top, height),
                "body_bottom": price_to_y(min(open_price, close_price), lo, hi, top, height),
            }
        )
    return layout
