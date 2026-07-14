from __future__ import annotations

import math

from .models import AnalysisResult, ComparisonRow, Measurement
from .policy import flip_hint, spectrum


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _positive_finite_float(value: object) -> float | None:
    number = _finite_float(value)
    return number if number is not None and number > 0 else None


def _positive_finite_int(value: object) -> int | None:
    number = _finite_float(value)
    if number is None or number <= 0:
        return None
    if not number.is_integer():
        return None
    return int(number)


def _safe_int(
    value: object, default: int = 0, minimum: int | None = None, maximum: int | None = None
) -> int:
    number = _finite_float(value)
    result = default if number is None else int(round(number))
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def build_comparison_rows(entries: list[dict]) -> list[ComparisonRow]:
    """把已深度分析的股票组装成横向对比行（含各档强度提示与浮动盈亏），按综合分降序。

    每个 entry 含：result(AnalysisResult)、measurement(Measurement)、risk(str)、
    cost(float|None)、shares(int|None)。无 measurement 的项应由调用方先过滤。
    """
    rows: list[ComparisonRow] = []
    for entry in entries:
        result: AnalysisResult = entry["result"]
        measurement: Measurement = entry["measurement"]
        cost = _positive_finite_float(entry.get("cost"))
        shares = _positive_finite_int(entry.get("shares"))
        last = _finite_float(result.last)
        change_pct = _finite_float(result.change_pct)
        pl_pct: float | None = None
        pl_amount: float | None = None
        if cost is not None and last is not None:
            pl_pct = (last - cost) / cost * 100
            if shares is not None:
                pl_amount = (last - cost) * shares
        rows.append(
            ComparisonRow(
                code=result.symbol.display,
                name=result.name,
                last=last,
                change_pct=change_pct,
                score=_safe_int(result.score),
                confidence=_safe_int(result.confidence, minimum=0, maximum=100),
                risk=entry.get("risk", ""),
                position=_safe_int(result.suggested_position, minimum=0, maximum=100),
                level_hint=flip_hint(spectrum(measurement, 0)),
                action=result.action,
                cost=cost,
                pl_pct=pl_pct,
                pl_amount=pl_amount,
            )
        )
    rows.sort(key=lambda r: (-r.score, r.code))
    return rows
