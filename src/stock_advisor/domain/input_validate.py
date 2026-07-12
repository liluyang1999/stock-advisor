"""输入解析与选股可调项校验——纯函数。"""
from __future__ import annotations

import math

from .formatting import _format_number


def _parse_optional_positive(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def _parse_optional_positive_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not number.is_integer():
        return None
    value = int(number)
    return value if value > 0 else None


def _parse_alert_threshold(text: str) -> float | None:
    try:
        value = float(text.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def is_partial_number(text: str, allow_negative: bool) -> bool:
    """数字输入框逐字符校验：允许构造中的数字（空串、单独小数点、允许时的负号）。

    用于 ttk.Spinbox 的 key 级校验，从源头挡住字母/多余符号，而不是等到提交才报错。
    """
    if text in ("", "."):
        return True
    body = text
    if body[0] == "-":
        if not allow_negative:
            return False
        body = body[1:]
    if body in ("", "."):
        return True
    if body.count(".") > 1:
        return False
    return all(ch.isdigit() or ch == "." for ch in body)


def validate_tunable(label: str, raw: str, minimum: float, maximum: float) -> float:
    """校验单个选股参数；非法时抛出可直接展示给用户的 ValueError，合法时返回数值。

    覆盖三种“明显错误”：留空、非数字、超出 [minimum, maximum] 区间（如推荐数量必须在 5~30 只）。
    """
    text = raw.strip()
    lo, hi = _format_number(minimum), _format_number(maximum)
    if not text:
        raise ValueError(f"“{label}”不能为空，请填写 {lo}~{hi} 之间的数字。")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"“{label}”必须是数字，请填写 {lo}~{hi} 之间的数值。") from None
    if not math.isfinite(value):
        raise ValueError(f"“{label}”必须是数字，请填写 {lo}~{hi} 之间的数值。")
    if value < minimum or value > maximum:
        raise ValueError(f"“{label}”必须在 {lo}~{hi} 之间，当前填写的是 {_format_number(value)}。")
    return value
