"""输入解析与选股可调项校验——纯函数。"""

from __future__ import annotations

import math


def parse_optional_positive(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def parse_optional_positive_int(text: str) -> int | None:
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


def parse_alert_threshold(text: str) -> float | None:
    try:
        value = float(text.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None
