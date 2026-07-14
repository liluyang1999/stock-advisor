from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal
from statistics import mean, pstdev

from .models import (
    STANDARD_LEVEL,
    AnalysisResult,
    DailyBar,
    Decision,
    FactorScore,
    IndicatorSnapshot,
    Measurement,
    Quote,
)
from .policy import decide


def moving_average(values: list[float], window: int) -> float | None:
    if window <= 0 or len(values) < window:
        return None
    recent = values[-window:]
    if not _all_finite(recent):
        return None
    return mean(recent)


def exponential_moving_average(values: list[float], period: int) -> float | None:
    series = _ema_series(values, period)
    if not series:
        return None
    return series[-1]


def macd_snapshot(values: list[float]) -> tuple[float, float, float] | None:
    if len(values) < 35 or not _all_finite(values):
        return None
    ema12 = _ema_series(values, 12)
    ema26 = _ema_series(values, 26)
    if len(ema12) < len(ema26):
        return None
    aligned_ema12 = ema12[-len(ema26) :]
    macd_line = [fast - slow for fast, slow in zip(aligned_ema12, ema26, strict=True)]
    signal_series = _ema_series(macd_line, 9)
    if not signal_series:
        return None
    macd = macd_line[-1]
    signal = signal_series[-1]
    histogram = macd - signal
    return macd, signal, histogram


def bollinger_position(values: list[float], last: float, window: int = 20) -> float | None:
    if window <= 0 or len(values) < window or not _finite_number(last):
        return None
    recent = values[-window:]
    if not _all_finite(recent):
        return None
    center = mean(recent)
    deviation = pstdev(recent)
    if deviation == 0:
        return 0.5
    upper = center + 2 * deviation
    lower = center - 2 * deviation
    span = upper - lower
    if span <= 0:
        return None
    return (last - lower) / span


def average_true_range_percent(
    history: list[DailyBar], last: float, period: int = 14
) -> float | None:
    if period <= 0 or len(history) < period + 1 or not _finite_positive(last):
        return None
    ranges: list[float] = []
    recent = history[-period - 1 :]
    previous_close = float(recent[0].close)
    if not _finite_positive(previous_close):
        return None
    for bar in recent[1:]:
        high, low, close = float(bar.high), float(bar.low), float(bar.close)
        if not all(_finite_positive(value) for value in (high, low, close)):
            return None
        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )
        ranges.append(true_range)
        previous_close = close
    if not ranges:
        return None
    return mean(ranges) / last * 100


def support_resistance(
    history: list[DailyBar], window: int = 20
) -> tuple[float | None, float | None]:
    if window <= 0:
        return None, None
    recent = history[-window:]
    if not recent:
        return None, None
    lows = [float(bar.low) for bar in recent if _finite_positive(bar.low)]
    highs = [float(bar.high) for bar in recent if _finite_positive(bar.high)]
    if not lows or not highs:
        return None, None
    return min(lows), max(highs)


def rsi(values: list[float], period: int = 14) -> float | None:
    if period <= 0 or len(values) < period + 1:
        return None
    recent_values = values[-period - 1 :]
    if not _all_finite(recent_values):
        return None

    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(recent_values[:-1], recent_values[1:], strict=True):
        delta = current - previous
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        elif delta < 0:
            gains.append(0.0)
            losses.append(abs(delta))
        else:
            gains.append(0.0)
            losses.append(0.0)

    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def measure(quote: Quote, history: list[DailyBar]) -> Measurement:
    """客观测量层：算指标 + 8 因子 + 风控扣分 + 置信度，结果与决策档位无关。"""
    quote = _clean_quote(quote)
    history = clean_history(history)
    # 报价是 Decimal（精确 2 位）；指标层是统计量,在此边界一次性转 float,不回流到金额/价格。
    last_f = float(quote.last)
    closes = [float(bar.close) for bar in history if _finite_positive(bar.close)]
    if not closes or abs(closes[-1] - last_f) / max(last_f, 0.01) > 0.001:
        closes = closes + [last_f]

    ma5 = moving_average(closes, 5)
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)
    rsi14 = rsi(closes, 14)
    macd = macd_snapshot(closes)
    bollinger = bollinger_position(closes, last_f)
    atr_percent = average_true_range_percent(history, last_f)
    support, resistance = support_resistance(history)
    win_rate = _five_day_win_rate(closes)
    drawdown = _max_drawdown(closes[-20:])
    volume_ratio = _volume_ratio(quote, history)
    intraday_position = _intraday_position(quote)

    indicators = IndicatorSnapshot(
        ma5=ma5,
        ma20=ma20,
        ma60=ma60,
        rsi14=rsi14,
        macd=macd[0] if macd else None,
        macd_signal=macd[1] if macd else None,
        macd_histogram=macd[2] if macd else None,
        bollinger_position=bollinger,
        atr_percent=atr_percent,
        support=support,
        resistance=resistance,
        five_day_win_rate=win_rate,
        max_drawdown_20=drawdown,
        volume_ratio=volume_ratio,
        intraday_position=intraday_position,
    )

    reasons: list[str] = []
    risks: list[str] = []
    factors: list[FactorScore] = []

    _extend_factor(factors, reasons, risks, *_score_moving_averages(last_f, ma5, ma20, ma60))
    _extend_factor(factors, reasons, risks, *_score_trend(closes, win_rate, drawdown))
    _extend_factor(factors, reasons, risks, *_score_momentum(rsi14, macd))
    _extend_factor(factors, reasons, risks, *_score_volume(quote, volume_ratio))
    _extend_factor(factors, reasons, risks, *_score_intraday(quote, intraday_position))
    _extend_factor(factors, reasons, risks, *_score_bollinger(bollinger))
    _extend_factor(factors, reasons, risks, *_score_support_resistance(last_f, support, resistance))
    _extend_factor(factors, reasons, risks, *_score_volatility(atr_percent))

    risk_penalty, risk_notes = _risk_penalty(quote, history)
    risks.extend(risk_notes)

    base_factor_sum = sum(item.score for item in factors)
    objective = base_factor_sum + risk_penalty
    if len(history) < 30:
        # 与 policy.policy_score 的降权取整口径保持一致（四舍五入而非截断），否则会打破
        # "L3 档决策分等于客观综合分"的既定承诺（见 policy.py 顶部文档）。
        objective = int(round(objective * 0.75))
        risks.append("历史样本少于30个交易日，模型置信度已下调。")
    objective = max(-100, min(100, int(round(objective))))

    confidence = _confidence(objective, history, indicators)
    expected_move = _expected_move_pct(quote, atr_percent)
    return Measurement(
        symbol=quote.symbol,
        name=quote.name,
        last=quote.last,
        change_pct=quote.change_pct,
        factors=factors,
        risk_penalty=risk_penalty,
        base_factor_sum=base_factor_sum,
        objective_score=objective,
        confidence=confidence,
        indicators=indicators,
        recent_closes=closes[-60:],
        reasons=reasons,
        risks=risks,
        history_len=len(history),
        expected_move_pct=expected_move,
    )


def build_analysis_result(m: Measurement, decision: Decision) -> AnalysisResult:
    """把客观测量 + 某档决策组装成展示用 AnalysisResult（兼容既有消费方）。"""
    factors = list(m.factors)
    if m.risk_penalty:
        factors.append(
            FactorScore("风控扣分", m.risk_penalty, 20, "谨慎", "跳空、振幅或回撤触发风险扣分。")
        )
    return AnalysisResult(
        symbol=m.symbol,
        name=m.name,
        action=decision.action,
        action_label=decision.action_label,
        score=decision.policy_score,
        confidence=m.confidence,
        last=m.last,
        change_pct=m.change_pct,
        suggested_position=decision.suggested_position,
        forecast_label=decision.forecast_label,
        expected_move_pct=m.expected_move_pct,
        indicators=m.indicators,
        factor_scores=_dedupe_factors(factors),
        recent_closes=m.recent_closes,
        reasons=decision.reasons,
        risks=decision.risks,
    )


def analyze_stock(
    quote: Quote, history: list[DailyBar], level: int = STANDARD_LEVEL
) -> AnalysisResult:
    """便捷包装：measure + decide(level) + 组装。默认档复现既有买/持/卖与综合分。"""
    m = measure(quote, history)
    return build_analysis_result(m, decide(m, level))


def _score_moving_averages(
    last: float, ma5: float | None, ma20: float | None, ma60: float | None
) -> tuple[FactorScore, list[str], list[str]]:
    if ma5 is None or ma20 is None:
        return (
            FactorScore("均线结构", 0, 28, "样本不足", "均线样本不足，趋势信号降权。"),
            ["均线样本不足，趋势信号降权。"],
            [],
        )

    price_vs_ma20 = (last - ma20) / max(abs(last), 0.01) * 100
    ma_spread = (ma5 - ma20) / max(abs(ma20), 0.01) * 100
    if (
        last > ma5 > ma20
        and price_vs_ma20 > 0.5
        and ma_spread > 0.2
        and (ma60 is None or ma20 > ma60)
    ):
        return (
            FactorScore("均线结构", 28, 28, "偏多", "价格站上短中期均线，均线结构偏多。"),
            ["价格站上短中期均线，均线结构偏多。"],
            [],
        )
    if (
        last < ma5 < ma20
        and price_vs_ma20 < -0.5
        and ma_spread < -0.2
        and (ma60 is None or ma20 < ma60)
    ):
        return (
            FactorScore("均线结构", -28, 28, "偏空", "价格跌破短中期均线，均线结构弱势。"),
            ["价格跌破短中期均线，均线结构弱势。"],
            [],
        )
    if price_vs_ma20 > 0.35:
        return (
            FactorScore(
                "均线结构", 8, 28, "略偏多", "价格位于20日均线上方，但均线结构未完全共振。"
            ),
            ["价格位于20日均线上方，但均线结构未完全共振。"],
            [],
        )
    if price_vs_ma20 < -0.35:
        return (
            FactorScore("均线结构", -8, 28, "略偏空", "价格低于20日均线，短线需防守。"),
            ["价格低于20日均线，短线需防守。"],
            [],
        )
    return FactorScore("均线结构", 0, 28, "中性", "价格贴近中期均线，趋势方向暂不清晰。"), [], []


def _score_trend(
    closes: list[float], win_rate: float | None, drawdown: float | None
) -> tuple[FactorScore, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    if len(closes) >= 25:
        recent_ma5 = moving_average(closes, 5)
        previous_ma5 = moving_average(closes[-25:-5], 5)
        if recent_ma5 is not None and previous_ma5 is not None:
            slope = (recent_ma5 - previous_ma5) / max(abs(previous_ma5), 0.01) * 100
            if slope > 2:
                score += 12
                reasons.append("短期趋势斜率向上，动量延续。")
            elif slope < -2:
                score -= 12
                reasons.append("短期趋势斜率向下，动量走弱。")
    if len(closes) >= 40:
        recent_ma20 = moving_average(closes, 20)
        previous_ma20 = moving_average(closes[-40:-20], 20)
        if recent_ma20 is not None and previous_ma20 is not None:
            slope = (recent_ma20 - previous_ma20) / max(abs(previous_ma20), 0.01) * 100
            if slope > 1:
                score += 8
                reasons.append("20日趋势抬升，中期方向偏多。")
            elif slope < -1:
                score -= 8
                reasons.append("20日趋势下行，中期方向偏空。")
    if win_rate is not None:
        if win_rate >= 0.7:
            score += 5
            reasons.append(f"近5日上涨胜率{win_rate:.0%}，短线节奏偏强。")
        elif win_rate <= 0.3:
            score -= 5
            reasons.append(f"近5日上涨胜率{win_rate:.0%}，短线节奏偏弱。")
    if drawdown is not None and drawdown > 8:
        score -= 4
        risks.append(f"20日最大回撤约{drawdown:.1f}%，趋势修复需要时间。")
    verdict = "偏多" if score > 6 else "偏空" if score < -6 else "中性"
    return (
        FactorScore(
            "趋势质量", score, 25, verdict, "综合短期斜率、20日斜率、近5日胜率和20日回撤。"
        ),
        reasons,
        risks,
    )


def _score_momentum(
    rsi14: float | None, macd: tuple[float, float, float] | None
) -> tuple[FactorScore, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    if rsi14 is None:
        risks.append("RSI样本不足，动量信号未启用。")
    elif 52 <= rsi14 <= 68:
        score += 8
        reasons.append(f"RSI14={rsi14:.1f}，动量健康但未明显过热。")
    elif 32 <= rsi14 < 45:
        score -= 8
        reasons.append(f"RSI14={rsi14:.1f}，反弹动量偏弱。")
    elif rsi14 > 76:
        score -= 6
        risks.append(f"RSI14={rsi14:.1f}，短线存在过热回撤风险。")
    elif rsi14 < 24:
        score -= 4
        risks.append(f"RSI14={rsi14:.1f}，弱势超卖不等于立即反转。")

    if macd is not None:
        macd_line, signal, histogram = macd
        min_strength = 0.001
        if abs(histogram) / max(abs(macd_line), 0.01) < 0.08 or abs(histogram) < min_strength:
            score += 0
        elif macd_line > signal and histogram > 0:
            score += 10
            reasons.append("MACD柱线为正且快线强于信号线，动量确认偏多。")
        elif macd_line < signal and histogram < 0:
            score -= 10
            reasons.append("MACD柱线为负且快线弱于信号线，动量确认偏空。")
    else:
        risks.append("MACD样本不足，趋势动量确认降权。")

    verdict = "偏多" if score > 6 else "偏空" if score < -6 else "中性"
    return (
        FactorScore("动量指标", score, 18, verdict, "综合 RSI14 与 MACD 快慢线/柱线。"),
        reasons,
        risks,
    )


def _score_volume(
    quote: Quote, volume_ratio: float | None
) -> tuple[FactorScore, list[str], list[str]]:
    if volume_ratio is None:
        return (
            FactorScore("量能确认", 0, 14, "样本不足", "缺少量能样本，成交确认信号降权。"),
            ["缺少量能样本，成交确认信号降权。"],
            [],
        )
    if quote.change_pct > 0.5 and volume_ratio >= 1.5:
        return (
            FactorScore(
                "量能确认",
                14,
                14,
                "偏多",
                f"量能放大至近20日均量的{volume_ratio:.2f}倍，上涨得到成交确认。",
            ),
            [f"量能放大至近20日均量的{volume_ratio:.2f}倍，上涨得到成交确认。"],
            [],
        )
    if quote.change_pct < -0.5 and volume_ratio >= 1.3:
        return (
            FactorScore(
                "量能确认",
                -14,
                14,
                "偏空",
                f"下跌伴随量能放大至{volume_ratio:.2f}倍，抛压需要警惕。",
            ),
            [f"下跌伴随量能放大至{volume_ratio:.2f}倍，抛压需要警惕。"],
            [],
        )
    if volume_ratio < 0.65:
        return (
            FactorScore(
                "量能确认",
                -4,
                14,
                "低量",
                f"量能仅为近20日均量的{volume_ratio:.2f}倍，信号可靠性偏低。",
            ),
            [f"量能仅为近20日均量的{volume_ratio:.2f}倍，信号可靠性偏低。"],
            [],
        )
    return (
        FactorScore(
            "量能确认", 0, 14, "中性", f"量能为近20日均量的{volume_ratio:.2f}倍，尚未形成强确认。"
        ),
        [],
        [],
    )


def _score_intraday(
    quote: Quote, position: float | None
) -> tuple[FactorScore, list[str], list[str]]:
    if position is None:
        return (
            FactorScore("日内位置", 0, 12, "无效", "当日高低价区间无效，日内位置未参与评分。"),
            [],
            ["当日高低价区间无效，日内位置未参与评分。"],
        )
    if quote.change_pct >= 0.8 and position >= 0.72:
        return (
            FactorScore("日内位置", 12, 12, "强势", "当前价靠近当日高位，日内承接较强。"),
            ["当前价靠近当日高位，日内承接较强。"],
            [],
        )
    if quote.change_pct <= -0.8 and position <= 0.28:
        return (
            FactorScore("日内位置", -12, 12, "弱势", "当前价贴近当日低位，日内走势弱势。"),
            ["当前价贴近当日低位，日内走势弱势。"],
            [],
        )
    if position < 0.2:
        return (
            FactorScore("日内位置", -5, 12, "偏弱", "当前价处于日内区间低位。"),
            [],
            ["当前价处于日内区间低位，需防止尾盘继续走弱。"],
        )
    if position > 0.85:
        return (
            FactorScore("日内位置", 4, 12, "偏强", "当前价接近日内高位。"),
            [],
            ["当前价接近日内高位，追高成本较敏感。"],
        )
    return FactorScore("日内位置", 0, 12, "中性", "当前价处于日内区间中部。"), [], []


def _score_bollinger(position: float | None) -> tuple[FactorScore, list[str], list[str]]:
    if position is None:
        return (
            FactorScore("布林位置", 0, 8, "样本不足", "布林带样本不足。"),
            [],
            ["布林带样本不足，波动区间信号未启用。"],
        )
    if 0.55 <= position <= 0.9:
        return (
            FactorScore(
                "布林位置",
                6,
                8,
                "健康偏强",
                f"价格处在布林通道{position:.0%}位置，偏强但未明显越界。",
            ),
            [f"布林带位置{position:.0%}，价格偏强但未明显越界。"],
            [],
        )
    if position > 1.05:
        return (
            FactorScore("布林位置", -6, 8, "过热", f"价格突破布林上轨较多，位置{position:.0%}。"),
            [],
            ["价格明显高于布林上轨，短线追高风险增加。"],
        )
    if position < -0.05:
        return (
            FactorScore("布林位置", -6, 8, "破位", f"价格跌出布林下轨，位置{position:.0%}。"),
            ["价格跌出布林下轨，弱势延续风险较高。"],
            [],
        )
    if position < 0.25:
        return (
            FactorScore("布林位置", -3, 8, "偏弱", f"价格处在布林通道{position:.0%}位置。"),
            ["布林带位置偏低，短线承压。"],
            [],
        )
    return (
        FactorScore("布林位置", 0, 8, "中性", f"布林带位置{position:.0%}，方向信号一般。"),
        [],
        [],
    )


def _score_support_resistance(
    last: float, support: float | None, resistance: float | None
) -> tuple[FactorScore, list[str], list[str]]:
    if support is None or resistance is None or last <= 0:
        return (
            FactorScore("支撑压力", 0, 8, "样本不足", "支撑压力样本不足。"),
            [],
            ["支撑/压力位样本不足。"],
        )
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    if last >= resistance * 1.005:
        score += 8
        reasons.append("价格接近或突破20日压力位，若量能配合则偏多。")
    elif last <= support * 1.01:
        score -= 8
        risks.append("价格接近20日支撑位，若跌破需控制回撤。")
    else:
        upper_room = (resistance - last) / last * 100
        lower_room = (last - support) / last * 100
        if upper_room > lower_room * 1.5:
            score += 3
            reasons.append("上方至压力位空间大于下方支撑风险，赔率略偏正。")
        elif lower_room > upper_room * 1.5:
            score -= 3
            risks.append("下方支撑距离较远，回撤空间需要留意。")
    verdict = "偏多" if score > 0 else "偏空" if score < 0 else "中性"
    return (
        FactorScore(
            "支撑压力", score, 8, verdict, f"20日支撑约{support:.2f}，压力约{resistance:.2f}。"
        ),
        reasons,
        risks,
    )


def _score_volatility(atr_percent: float | None) -> tuple[FactorScore, list[str], list[str]]:
    if atr_percent is None:
        return (
            FactorScore("波动风险", 0, 10, "样本不足", "ATR样本不足。"),
            [],
            ["ATR样本不足，波动风险估计降权。"],
        )
    if atr_percent > 6:
        return (
            FactorScore("波动风险", -10, 10, "高波动", f"ATR约{atr_percent:.2f}%，短线波动偏大。"),
            [],
            [f"ATR约{atr_percent:.2f}%，短线波动偏大，仓位应下调。"],
        )
    if atr_percent > 3.5:
        return (
            FactorScore("波动风险", -4, 10, "中高波动", f"ATR约{atr_percent:.2f}%，波动略高。"),
            [],
            [f"ATR约{atr_percent:.2f}%，注意设置止损。"],
        )
    return (
        FactorScore("波动风险", 4, 10, "可控", f"ATR约{atr_percent:.2f}%，波动处于可控区间。"),
        ["近期真实波动率处于可控区间。"],
        [],
    )


def _risk_penalty(quote: Quote, history: list[DailyBar]) -> tuple[int, list[str]]:
    penalty = 0
    risks: list[str] = []
    if quote.previous_close > 0:
        gap = (quote.open - quote.previous_close) / quote.previous_close * 100
        if gap > 4:
            penalty -= 8
            risks.append(f"高开{gap:.2f}%，短线回落风险上升。")
        elif gap < -4:
            penalty -= 6
            risks.append(f"低开{abs(gap):.2f}%，资金情绪偏弱。")
    if quote.low > 0:
        amplitude = (quote.high - quote.low) / quote.low * 100
        if amplitude > 7:
            penalty -= 6
            risks.append(f"当日振幅{amplitude:.2f}%，波动风险较高。")
    if history:
        recent_high = max(bar.high for bar in history[-20:])
        if float(quote.last) < float(recent_high) * 0.88:
            penalty -= 4
            risks.append("价格距离20日高点回撤较深，趋势修复仍需时间。")
    return penalty, risks


def _ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period or period <= 0:
        return []
    smoothing = 2 / (period + 1)
    ema = mean(values[:period])
    result = [ema]
    for value in values[period:]:
        ema = value * smoothing + ema * (1 - smoothing)
        result.append(ema)
    return result


def _five_day_win_rate(closes: list[float]) -> float | None:
    if len(closes) < 6:
        return None
    changes = [
        current > previous for previous, current in zip(closes[-6:-1], closes[-5:], strict=True)
    ]
    return sum(1 for item in changes if item) / len(changes)


def _max_drawdown(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    peak = values[0]
    max_drop = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drop = max(max_drop, (peak - value) / peak * 100)
    return max_drop


def _volume_ratio(quote: Quote, history: list[DailyBar]) -> float | None:
    recent = [bar.volume for bar in history[-20:] if bar.volume > 0]
    if len(recent) < 5:
        return None
    return quote.volume / mean(recent)


def _intraday_position(quote: Quote) -> float | None:
    span = quote.high - quote.low
    if span <= 0:
        return None
    return max(0.0, min(1.0, float((quote.last - quote.low) / span)))


def _confidence(score: int, history: list[DailyBar], indicators: IndicatorSnapshot) -> int:
    base = 42 + min(abs(score) * 0.42, 32)
    data_bonus = min(len(history), 90) / 90 * 12
    for value in (
        indicators.volume_ratio,
        indicators.ma60,
        indicators.macd_histogram,
        indicators.bollinger_position,
        indicators.atr_percent,
        indicators.support,
    ):
        if value is not None:
            data_bonus += 2
    if indicators.atr_percent is not None and indicators.atr_percent > 6:
        data_bonus -= 6
    return max(35, min(92, int(round(base + data_bonus))))


def _expected_move_pct(quote: Quote, atr_percent: float | None) -> float | None:
    if atr_percent is not None:
        return round(max(0.8, min(12.0, atr_percent)), 2)
    if quote.low > 0:
        return round(max(0.8, min(12.0, float((quote.high - quote.low) / quote.low * 100))), 2)
    return None


def _extend_factor(
    factors: list[FactorScore],
    reasons: list[str],
    risks: list[str],
    factor: FactorScore,
    factor_reasons: list[str],
    factor_risks: list[str],
) -> None:
    factors.append(factor)
    reasons.extend(factor_reasons)
    risks.extend(factor_risks)


def _dedupe_factors(items: list[FactorScore]) -> list[FactorScore]:
    seen: set[str] = set()
    result: list[FactorScore] = []
    for item in items:
        if item.name in seen:
            continue
        seen.add(item.name)
        result.append(item)
    return result


def _finite_number(value: float | int | Decimal) -> bool:
    return math.isfinite(float(value))


def _all_finite(values: list[float] | tuple[float, ...]) -> bool:
    return all(_finite_number(value) for value in values)


def _finite_positive(value: float | int | Decimal) -> bool:
    return _finite_number(value) and float(value) > 0


def _finite_nonnegative(value: float | int | Decimal) -> bool:
    return _finite_number(value) and float(value) >= 0


def _clean_quote(quote: Quote) -> Quote:
    required_prices = (
        ("最新价", quote.last),
        ("开盘价", quote.open),
        ("最高价", quote.high),
        ("最低价", quote.low),
        ("昨收价", quote.previous_close),
    )
    for label, value in required_prices:
        if not _finite_positive(value):
            raise ValueError(f"{quote.symbol.display} 实时行情{label}无效。")
    change_pct = quote.change_pct
    if not _finite_number(change_pct):
        change_pct = float((quote.last - quote.previous_close) / quote.previous_close * 100)
    return replace(
        quote,
        high=max(quote.high, quote.open, quote.last),
        low=min(quote.low, quote.open, quote.last),
        volume=max(0, int(quote.volume)) if _finite_number(quote.volume) else 0,
        amount=max(0.0, quote.amount) if _finite_number(quote.amount) else 0.0,
        turnover_rate=max(0.0, quote.turnover_rate) if _finite_number(quote.turnover_rate) else 0.0,
        change_pct=change_pct,
    )


def clean_history(history: list[DailyBar]) -> list[DailyBar]:
    rows: list[DailyBar] = []
    for bar in history:
        if not all(_finite_positive(value) for value in (bar.open, bar.close, bar.high, bar.low)):
            continue
        if not all(
            _finite_nonnegative(value) for value in (bar.volume, bar.amount, bar.turnover_rate)
        ):
            continue
        pct_change = bar.pct_change if _finite_number(bar.pct_change) else 0.0
        high = max(bar.high, bar.open, bar.close)
        low = min(bar.low, bar.open, bar.close)
        rows.append(
            replace(
                bar,
                high=high,
                low=low,
                volume=max(0, int(bar.volume)),
                amount=max(0.0, bar.amount),
                turnover_rate=max(0.0, bar.turnover_rate),
                pct_change=pct_change,
            )
        )
    return rows
