from __future__ import annotations

import math

from .models import (
    Action,
    CORE_DISCLAIMER,
    Decision,
    LevelSpec,
    Measurement,
    PositionPlan,
    SpectrumCell,
    STANDARD_LEVEL,
)


# 决策强度档位表（与设计规格一致）。
# 阈值非对称且「旋转」：越保守买入门槛越高、卖出门槛越低（快出）；越激进买入门槛越低、
# 卖出门槛越低（扛单）。L3 标准等同既有行为。
LEVELS: dict[int, LevelSpec] = {
    1: LevelSpec(1, "稳健", 40, -15, 1.6, 70, 0.005, 0.30, 2.5),
    2: LevelSpec(2, "稳进", 33, -19, 1.3, 60, 0.0075, 0.45, 2.2),
    3: LevelSpec(3, "标准", 25, -25, 1.0, 0, 0.01, 0.60, 2.0),
    4: LevelSpec(4, "积极", 18, -33, 0.8, 0, 0.015, 0.75, 1.7),
    5: LevelSpec(5, "激进", 12, -42, 0.6, 0, 0.02, 0.90, 1.5),
}

_ACTION_LABEL = {"BUY": "买入/加仓", "SELL": "卖出/减仓", "HOLD": "继续持有/观望"}
_DISCLAIMER = CORE_DISCLAIMER  # 权威来源见 models.CORE_DISCLAIMER，勿在此处另写措辞。


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def clamp_level(level: int) -> int:
    try:
        value = float(level)
    except (TypeError, ValueError):
        return STANDARD_LEVEL
    if not math.isfinite(value):
        return STANDARD_LEVEL
    return max(1, min(5, int(value)))


def level_spec(level: int) -> LevelSpec:
    return LEVELS[clamp_level(level)]


def _finite_number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _finite_positive(value: object, default: float | None = None) -> float | None:
    number = _finite_number(value, math.nan)
    if math.isfinite(number) and number > 0:
        return number
    return default


def _confidence_value(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return max(0.0, min(100.0, number))


def _history_len(value: object) -> int:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    return max(0, int(number))


def policy_score(m: Measurement, level: int) -> int:
    """按档位对客观因子重新加权得到决策分。L3 时等于客观综合分。"""
    spec = level_spec(level)
    score = _finite_number(m.base_factor_sum) + _finite_number(m.risk_penalty) * spec.risk_weight
    if _history_len(m.history_len) < 30:
        score *= 0.75
    return max(-100, min(100, int(round(score))))


def _stop_pct(m: Measurement) -> float:
    """止损距离%：基于真实波动率 ATR，缺失时回退到常态波动或默认 3%。"""
    atr = _finite_positive(m.indicators.atr_percent)
    if atr is None:
        atr = _finite_positive(m.expected_move_pct, 3.0)
    return max(2.0, min(12.0, 1.8 * atr))


def size_fraction(m: Measurement, level: int) -> float:
    """建议投入比例（占本金，0..仓位上限）。仅买入给多头仓位。"""
    spec = level_spec(level)
    score = policy_score(m, level)
    if score < spec.t_buy:
        return 0.0
    confidence = _confidence_value(m.confidence)
    if confidence is None:
        return 0.0
    if spec.confidence_gate and confidence < spec.confidence_gate:
        return 0.0
    stop = _stop_pct(m) / 100.0
    strength = max(0.4, min(1.0, abs(score) / 55.0))
    conf = max(0.5, min(1.0, confidence / 100.0))
    frac = (spec.risk_budget / stop) * strength * conf
    return max(0.0, min(spec.position_cap, frac))


def position_plan(m: Measurement, level: int, capital: float) -> PositionPlan:
    """结合本金把投入比例落到绝对股数/止损/止盈/最大亏损。A股 1 手=100 股。"""
    spec = level_spec(level)
    entry = _finite_positive(m.last)
    if entry is None:
        return PositionPlan(
            fraction=0.0,
            shares=0,
            lots=0,
            entry=0.0,
            stop_price=0.0,
            stop_pct=0.0,
            target_price=0.0,
            target_pct=0.0,
            reward_risk=spec.reward_risk,
            cost=0.0,
            max_loss=0.0,
            max_loss_pct=0.0,
            note="价格无效，无法计算仓位。",
        )
    stop_pct = _stop_pct(m)
    stop_price = round(entry * (1 - stop_pct / 100.0), 2)
    target_pct = stop_pct * spec.reward_risk
    target_price = round(entry * (1 + target_pct / 100.0), 2)
    frac = size_fraction(m, level)
    note = ""
    if not math.isfinite(capital) or capital <= 0:
        frac = 0.0
        note = "本金需大于0，无法计算买入仓位。"
        shares = 0
    elif frac <= 0:
        if policy_score(m, level) >= spec.t_buy and _confidence_value(m.confidence) is None:
            note = "把握程度无效，不建议新建多头仓位。"
        else:
            note = "本档观望/减仓，不建议新建多头仓位。"
        shares = 0
    else:
        shares = int(capital * frac / entry // 100) * 100
        if shares <= 0:
            note = f"本金不足以买入 1 手（约 {entry * 100:.0f} 元）。"
    if shares <= 0:
        frac = 0.0
    cost = shares * entry
    max_loss = shares * (entry - stop_price)
    actual_fraction = cost / capital if math.isfinite(capital) and capital > 0 else 0.0
    return PositionPlan(
        fraction=round(actual_fraction, 4),
        shares=shares,
        lots=shares // 100,
        entry=entry,
        stop_price=stop_price,
        stop_pct=round(stop_pct, 2),
        target_price=target_price,
        target_pct=round(target_pct, 2),
        reward_risk=spec.reward_risk,
        cost=round(cost, 2),
        max_loss=round(max_loss, 2),
        max_loss_pct=round(max_loss / capital, 4) if math.isfinite(capital) and capital > 0 else 0.0,
        note=note,
    )


def _action(score: int, confidence: int, spec: LevelSpec) -> tuple[Action, str]:
    if score >= spec.t_buy:
        confidence_value = _confidence_value(confidence)
        if confidence_value is None:
            return "HOLD", "把握程度无效，本档不建议买入。"
        confidence = int(round(confidence_value))
        if spec.confidence_gate and confidence < spec.confidence_gate:
            return "HOLD", "信号达到买入线但把握不足，本档要求更高确认，暂观望。"
        return "BUY", ""
    if score <= spec.t_sell:
        return "SELL", ""
    return "HOLD", ""


def _forecast_label(action: Action, score: int, expected_move: float | None) -> str:
    move_value = _finite_positive(expected_move)
    move = f"；常态波动约±{move_value:.2f}%" if move_value is not None else ""
    if action == "BUY":
        strength = "强偏多" if score >= 55 else "偏多"
        return f"{strength}，适合等待回踩或放量确认后分批参与{move}"
    if action == "SELL":
        strength = "强偏空" if score <= -55 else "偏空"
        return f"{strength}，优先控制回撤，反弹不放量时降低仓位{move}"
    return f"中性震荡，等待突破压力或跌破支撑后的方向确认{move}"


def spectrum(m: Measurement, current_level: int) -> list[SpectrumCell]:
    """对 5 档分别决策，返回供「强度光谱尺」渲染的单元（含当前档高亮）。"""
    cur = clamp_level(current_level)
    cells: list[SpectrumCell] = []
    for lv in range(1, 6):
        spec = LEVELS[lv]
        cells.append(SpectrumCell(lv, spec.name, decide(m, lv).action, lv == cur))
    return cells


def flip_hint(cells: list[SpectrumCell]) -> str:
    """一句话点出该股在哪一档发生买/卖翻转。"""
    buys = [c for c in cells if c.action == "BUY"]
    sells = [c for c in cells if c.action == "SELL"]
    if len(buys) == 5:
        return "各档均建议买入 —— 信号较强。"
    if buys:
        return f"需到「{buys[0].name}」及以上才建议买入；更保守则观望。"
    if len(sells) == 5:
        return "各档均建议卖出/减仓 —— 风险偏高。"
    if sells:
        return f"「{sells[-1].name}」及以下偏向卖出/减仓；更激进则倾向持有。"
    return "各档均建议观望，方向尚不明朗。"


def decide(m: Measurement, level: int = STANDARD_LEVEL) -> Decision:
    spec = level_spec(level)
    score = policy_score(m, level)
    confidence = int(max(0, min(100, round(_finite_number(m.confidence)))))
    action, gate_note = _action(score, confidence, spec)
    reasons = list(m.reasons) or ["有效信号不足，模型保持中性。"]
    risks = list(m.risks)
    if gate_note:
        risks.insert(0, gate_note)
    if action == "HOLD" and not gate_note:
        risks.append("多空证据分歧，等待方向确认比追涨杀跌更稳妥。")
    risks.append(_DISCLAIMER)
    suggested = int(round(size_fraction(m, level) * 100))
    return Decision(
        level=spec.level,
        action=action,
        action_label=_ACTION_LABEL[action],
        policy_score=score,
        suggested_position=suggested,
        forecast_label=_forecast_label(action, score, m.expected_move_pct),
        reasons=_dedupe(reasons),
        risks=_dedupe(risks),
    )
