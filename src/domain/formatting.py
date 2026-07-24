"""数值强制、低层格式化、风险分级与文本谓词——纯函数,供 view_text / view_format 复用。"""

from __future__ import annotations

import math

from .models import AnalysisResult
from .numeric import (
    finite_float as _finite_float,
    positive_finite_float as _positive_finite_float,
    safe_int as _safe_int,
)


def _fmt_rate_percent(value: object, missing: str = "样本不足") -> str:
    number = _finite_float(value)
    if number is None:
        return missing
    return f"{number * 100:.0f}%"


def _fmt_backtest_return(value: object, missing: str = "样本不足") -> str:
    return _fmt_percent_points(value, signed=True, missing=missing)


def _fmt_backtest_excess(value: object, baseline: object, missing: str = "样本不足") -> str:
    number = _finite_float(value)
    base = _finite_float(baseline)
    if number is None or base is None:
        return missing
    return _fmt_backtest_return(number - base, missing=missing)


def _fmt_decimal(value: object, digits: int = 2, signed: bool = False, missing: str = "—") -> str:
    number = _finite_float(value)
    if number is None:
        return missing
    spec = f"{'+' if signed else ''}.{digits}f"
    return f"{number:{spec}}"


def _fmt_score_value(value: object, signed: bool = False) -> str:
    score = _safe_int(value, default=0)
    return f"{score:+d}" if signed else str(score)


def _fmt_plain_number(value: object, missing: str = "—") -> str:
    number = _finite_float(value)
    if number is None:
        return missing
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _fmt_whole_percent(value: object, missing: str = "—") -> str:
    number = _finite_float(value)
    if number is None:
        return missing
    return f"{max(0, min(100, int(round(number))))}%"


def _fmt_percent_points(
    value: object, digits: int = 2, signed: bool = False, missing: str = "—"
) -> str:
    number = _finite_float(value)
    if number is None:
        return missing
    spec = f"{'+' if signed else ''}.{digits}f"
    return f"{number:{spec}}%"


def _fmt_yi(value: object) -> str:
    number = _finite_float(value)
    if number is None:
        return "样本不足"
    return f"{number / 1.0e8:+.2f}亿"


def _flow_direction(value: object) -> str:
    number = _finite_float(value)
    if number is None:
        return "方向不明"
    return "净流入" if number >= 0 else "净流出"


def _fmt_amount(value: float | None) -> str:
    number = _positive_finite_float(value)
    if number is None:
        return "样本不足"
    if number >= 1.0e8:
        return f"{number / 1.0e8:.2f}亿"
    if number >= 1.0e4:
        return f"{number / 1.0e4:.0f}万"
    return f"{number:.0f}"


def _format_number(value: float) -> str:
    number = _finite_float(value)
    if number is None:
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _spin_step(param: object) -> float:
    kind = getattr(param, "kind", "float")
    maximum = getattr(param, "maximum", 100.0)
    if kind == "int":
        return 1.0
    return 0.1 if maximum <= 12 else 1.0


def risk_level(result: AnalysisResult) -> str:
    confidence = _finite_float(result.confidence)
    change_pct = _finite_float(result.change_pct)
    score = _finite_float(result.score)
    if confidence is None or change_pct is None or score is None:
        return "高"
    if confidence < 50 or len(result.risks) >= 5 or abs(change_pct) >= 7:
        return "高"
    if confidence < 68 or len(result.risks) >= 3 or abs(score) < 18:
        return "中"
    return "低"


def _number_from_cell(value: object, remove: str = "") -> float:
    text = str(value).replace(remove, "").replace("%", "").replace("+", "").strip()
    if not text:
        return 0.0
    try:
        number = float(text)
    except ValueError:
        return 0.0
    return number if math.isfinite(number) else 0.0


def _looks_risky(text: str) -> bool:
    keywords = ("风险", "注意", "谨慎", "跌破", "回撤", "失败", "暂时取不到", "不构成")
    return any(keyword in text for keyword in keywords)


def _looks_positive(text: str) -> bool:
    keywords = ("买入", "加仓", "偏积极", "略积极", "较好", "较强", "突破")
    return any(keyword in text for keyword in keywords)


def _looks_negative(text: str) -> bool:
    keywords = ("卖出", "减仓", "偏谨慎", "略谨慎", "较弱", "走弱", "跌破")
    return any(keyword in text for keyword in keywords)


def _fmt(value: float | None) -> str:
    number = _finite_float(value)
    if number is None:
        return "样本不足"
    return f"{number:.2f}"


def _fmt_percent(value: float | None) -> str:
    number = _finite_float(value)
    if number is None:
        return "样本不足"
    return f"{number * 100:.1f}%"


def _fmt_percent_value(value: float | None) -> str:
    number = _finite_float(value)
    if number is None:
        return "样本不足"
    return f"{number:.2f}%"
