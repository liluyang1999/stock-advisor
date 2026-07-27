"""比率 / 百分比 / 评分 / 统计指标数值的安全解析(float)。

全工程数值约定的一半:**比率、百分比、评分、统计指标(MA/MACD/RSI/ATR/布林…)用 float**
——它们本就是统计量,还要喂给 mean/pstdev/ema 等统计函数。**金额与报价用 Decimal**,见
[money.py](money.py);**数量用 int**。这些安全解析器此前在 chart/compare/formatting/alerts
各写一份,现收敛于此(单一真源)。
"""

from __future__ import annotations

import math


def finite_float(value: object) -> float | None:
    """转 float;bool / 非数 / 非有限(inf/nan)/ 溢出 → None。

    显式拒绝 bool:它是 int 的子类,``float(True) == 1.0``,少了这道防御 True/False 会被静默当成
    1.0/0.0 混进评分/阈值/涨跌幅——与 [money.py](money.py) 的 ``parse_money`` 同源约定。
    """
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError, OverflowError:
        return None
    return number if math.isfinite(number) else None


def positive_finite_float(value: object) -> float | None:
    number = finite_float(value)
    return number if number is not None and number > 0 else None


def nonnegative_finite_float(value: object) -> float | None:
    number = finite_float(value)
    return number if number is not None and number >= 0 else None


def positive_finite_int(value: object) -> int | None:
    number = finite_float(value)
    if number is None or number <= 0 or not number.is_integer():
        return None
    return int(number)


def safe_int(
    value: object, default: int = 0, minimum: int | None = None, maximum: int | None = None
) -> int:
    number = finite_float(value)
    result = default if number is None else int(round(number))
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result
