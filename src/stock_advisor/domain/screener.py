from __future__ import annotations

import math

from .models import FilterCriteria, MarketSnapshot, Recommendation

BOARD_SH_MAIN = "沪市主板"
BOARD_SZ_MAIN = "深市主板"
BOARD_CHINEXT = "创业板"
BOARD_STAR = "科创板"
BOARD_BJ = "北交所"
ALL_BOARDS: tuple[str, ...] = (BOARD_SH_MAIN, BOARD_SZ_MAIN, BOARD_CHINEXT, BOARD_STAR, BOARD_BJ)

OBJECTIVES: tuple[str, ...] = ("momentum", "breakout", "activity", "value", "rebound", "balanced")
OBJECTIVE_LABELS = {
    "momentum": "动量优先",
    "breakout": "放量突破",
    "activity": "活跃优先",
    "value": "价值优先",
    "rebound": "超跌企稳",
    "balanced": "综合稳健",
}


def board_of(snapshot: MarketSnapshot) -> str:
    code, market = snapshot.code, snapshot.market_id
    if market == "1":
        if code.startswith(("688", "689")):
            return BOARD_STAR
        return BOARD_SH_MAIN  # 60xxxx / 900xxx（沪市B股）
    if code.startswith(("300", "301")):
        return BOARD_CHINEXT
    if code.startswith(("92", "8", "4")):
        return BOARD_BJ
    return BOARD_SZ_MAIN  # 000 / 001 / 002 / 003


def _in_range(value: float | None, low: float | None, high: float | None) -> bool:
    value = _finite_optional(value)
    if low is not None and (value is None or value < low):
        return False
    if high is not None and (value is None or value > high):
        return False
    return True


def _finite_optional(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _finite_or(value: float | None, default: float) -> float:
    number = _finite_optional(value)
    return default if number is None else number


def _has_valid_required_snapshot_values(snapshot: MarketSnapshot) -> bool:
    required = (
        snapshot.price,
        snapshot.change_pct,
        snapshot.change,
        snapshot.amount,
        snapshot.amplitude,
        snapshot.turnover_rate,
    )
    return all(_finite_optional(value) is not None for value in required)


def passes(snapshot: MarketSnapshot, criteria: FilterCriteria) -> bool:
    if not _has_valid_required_snapshot_values(snapshot):
        return False
    if criteria.exclude_st and snapshot.is_st:
        return False
    pe_ttm = _finite_optional(snapshot.pe_ttm)
    if criteria.exclude_loss and (pe_ttm is None or pe_ttm <= 0):
        return False
    if criteria.boards and board_of(snapshot) not in criteria.boards:
        return False
    checks: tuple[tuple[float | None, float | None, float | None], ...] = (
        (float(snapshot.price), criteria.price_min, criteria.price_max),
        (snapshot.change_pct, criteria.change_pct_min, criteria.change_pct_max),
        (snapshot.amplitude, criteria.amplitude_min, criteria.amplitude_max),
        (snapshot.turnover_rate, criteria.turnover_min, criteria.turnover_max),
        (snapshot.volume_ratio, criteria.volume_ratio_min, criteria.volume_ratio_max),
        (snapshot.amount, criteria.amount_min, None),
        (snapshot.total_cap, criteria.total_cap_min, criteria.total_cap_max),
        (snapshot.float_cap, criteria.float_cap_min, criteria.float_cap_max),
        (snapshot.pe_ttm, criteria.pe_min, criteria.pe_max),
        (snapshot.pb, criteria.pb_min, criteria.pb_max),
        (snapshot.change_60d, criteria.change_60d_min, criteria.change_60d_max),
        (snapshot.change_ytd, criteria.change_ytd_min, criteria.change_ytd_max),
    )
    return all(_in_range(value, low, high) for value, low, high in checks)


def apply_filters(
    snapshots: list[MarketSnapshot], criteria: FilterCriteria
) -> list[MarketSnapshot]:
    return [snapshot for snapshot in snapshots if passes(snapshot, criteria)]


def _liquidity_bonus(amount: float) -> float:
    amount = _finite_or(amount, 0.0)
    if amount <= 0:
        return 0.0
    return min(amount / 1.0e8, 5.0)


def score_for(snapshot: MarketSnapshot, objective: str) -> float:
    cp = _finite_or(snapshot.change_pct, 0.0)
    vr = _finite_or(snapshot.volume_ratio, 1.0)
    turnover = _finite_or(snapshot.turnover_rate, 0.0)
    c60 = _finite_or(snapshot.change_60d, 0.0)
    cytd = _finite_or(snapshot.change_ytd, 0.0)
    speed = _finite_or(snapshot.speed, 0.0)
    amplitude = _finite_or(snapshot.amplitude, 0.0)
    amount = _finite_or(snapshot.amount, 0.0)
    pe = _finite_optional(snapshot.pe_ttm)
    pb = _finite_optional(snapshot.pb)

    if objective == "momentum":
        return cp + c60 * 0.3 + (vr - 1.0) * 5.0 + speed * 0.5
    if objective == "breakout":
        return cp * 0.8 + (vr - 1.0) * 12.0 + turnover * 0.3
    if objective == "activity":
        return turnover + (vr - 1.0) * 6.0 + _liquidity_bonus(amount)
    if objective == "value":
        pe_term = (20.0 - pe) if (pe is not None and pe > 0) else -15.0
        pb_term = (3.0 - pb) * 3.0 if (pb is not None and pb > 0) else -8.0
        return pe_term + pb_term + cp * 0.2
    if objective == "rebound":
        return (-c60) + cp * 0.5 - max(0.0, cytd) * 0.2
    if objective == "balanced":
        return cp * 0.4 + (vr - 1.0) * 3.0 - max(0.0, amplitude - 4.0) + _liquidity_bonus(amount)
    return cp


def rank(snapshots: list[MarketSnapshot], objective: str) -> list[tuple[float, MarketSnapshot]]:
    scored = [(_finite_or(score_for(snapshot, objective), 0.0), snapshot) for snapshot in snapshots]
    # 稳定排序：分数降序，分数相同按成交额降序，再按代码，保证结果可复现
    scored.sort(key=lambda pair: (-pair[0], -_finite_or(pair[1].amount, 0.0), pair[1].code))
    return scored


def _top_limit(value: object) -> int:
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return 0
    if not math.isfinite(number):
        return 0
    return max(0, int(number))


def recommend(
    snapshots: list[MarketSnapshot],
    criteria: FilterCriteria,
    objective: str,
    top_n: int = 20,
) -> list[Recommendation]:
    filtered = apply_filters(snapshots, criteria)
    scored = rank(filtered, objective)
    recommendations: list[Recommendation] = []
    for index, (score, snapshot) in enumerate(scored[: _top_limit(top_n)], start=1):
        recommendations.append(
            Recommendation(
                rank=index,
                snapshot=snapshot,
                screen_score=round(score, 2),
                board=board_of(snapshot),
            )
        )
    return recommendations
