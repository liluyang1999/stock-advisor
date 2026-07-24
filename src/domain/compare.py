from __future__ import annotations

from decimal import Decimal

from . import money
from .models import AnalysisResult, ComparisonRow, Measurement
from .numeric import (
    finite_float as _finite_float,
    positive_finite_int as _positive_finite_int,
    safe_int as _safe_int,
)
from .policy import flip_hint, spectrum


def build_comparison_rows(entries: list[dict]) -> list[ComparisonRow]:
    """把已深度分析的股票组装成横向对比行（含各档强度提示与浮动盈亏），按综合分降序。

    每个 entry 含：result(AnalysisResult)、measurement(Measurement)、risk(str)、
    cost(float|None)、shares(int|None)。无 measurement 的项应由调用方先过滤。
    """
    rows: list[ComparisonRow] = []
    for entry in entries:
        result: AnalysisResult = entry["result"]
        measurement: Measurement = entry["measurement"]
        cost = money.positive_money(entry.get("cost"))
        shares = _positive_finite_int(entry.get("shares"))
        last = money.parse_money(result.last)
        change_pct = _finite_float(result.change_pct)
        pl_pct: float | None = None
        pl_amount: Decimal | None = None
        if cost is not None and last is not None:
            pl_pct = float((last - cost) / cost * 100)
            if shares is not None:
                pl_amount = money.quantize_money((last - cost) * shares)
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
