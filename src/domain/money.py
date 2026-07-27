"""金额与价格的**精确**表示:统一 ``Decimal``,量化到 2 位小数(四舍五入 ROUND_HALF_UP)。

全工程数值约定的另一半:**金额与报价用 Decimal(2 位)**——价格、成本、本金、成交额、市值、
资金流、盈亏金额、仓位测算的价格与金额,均以此为准,存储(持久化写字符串)与计算全程不丢精度;
**数量用 int**;**比率 / 百分比 / 评分 / 统计指标用 float**(见 [numeric.py](numeric.py))。

float 只在把报价喂给统计函数(mean/pstdev/ema…)时于边界处产生,不回流到金额/价格。
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")


def quantize_money(value: Decimal) -> Decimal:
    """量化到 2 位小数,四舍五入(ROUND_HALF_UP,符合金额习惯;非 Python 默认的银行家舍入)。"""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _safe_quantize(number: Decimal) -> Decimal | None:
    """量化到 2 位,返回 None 而非抛异常:非有限,或过大以致量化结果的有效位数超出默认十进制
    上下文(28 位)——量化到 2 位会把有效位推到 (整数位+2),整数位 ≥27(约 ≥1e26)即触发
    ``InvalidOperation``。安全解析器据此把"读不出合法金额"统一表达为 None,不让调用方吃到异常。"""
    if not number.is_finite():
        return None
    try:
        return quantize_money(number)
    except InvalidOperation:
        return None


def to_money(value: Decimal | int | str | float) -> Decimal:
    """把**确知为金额/价格**的值转成 2 位小数 Decimal。

    float 先经 ``repr`` 取其最短往返十进制串,避免二进制误差(``repr(10.1) == '10.1'`` →
    Decimal('10.1') → 10.10),因此仅用于本就是两位小数的价格/金额,不用于任意 float 统计量。
    """
    if isinstance(value, Decimal):
        return quantize_money(value)
    if isinstance(value, float):
        value = repr(value)
    return quantize_money(Decimal(value))


def parse_money(value: object) -> Decimal | None:
    """安全解析为 2 位小数 Decimal;None / 空串 / "-" / 非数 / 非有限 / bool → None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return _safe_quantize(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        value = repr(value)
    text = str(value).strip()
    if text in ("", "-"):
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return _safe_quantize(number)


def positive_money(value: object) -> Decimal | None:
    """解析为正的 2 位小数金额;<=0 / 无法解析 → None(用于价格、成本、本金等必为正的量)。"""
    number = parse_money(value)
    return number if number is not None and number > ZERO_MONEY else None


def scaled_price(scaled: object, scale: int) -> Decimal | None:
    """东财 scaled 整数价 → 精确 2 位小数 Decimal(scaled / scale);非法 → None。

    源是整数、除数是 10 的幂,除法在 Decimal 下精确,再量化到 2 位即得报价。
    """
    if scaled is None or isinstance(scaled, bool):
        return None
    try:
        raw = Decimal(str(scaled))
    except InvalidOperation:
        return None
    if not raw.is_finite():
        return None
    if not scale:  # scale == 0 会让 raw / Decimal(0) 抛 DivisionByZero
        return None
    return _safe_quantize(raw / Decimal(scale))
