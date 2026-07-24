"""engine.py 防御性守卫与私有打分函数的行为锁定测试。

补齐 test_engine.py / test_measure.py 未覆盖的样本不足 / 非有限 / 边界分支：这些分支多数
只能对私有打分函数直接喂入构造输入才能触发（measure 的清洗层已保证价格有限为正，走不到），
与既有 test_measure.py 直接调用 `_score_bollinger` 的做法一致。断言全部照实证到的当前输出锁定。
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import make_history, make_quote

from domain.engine import (
    _clean_quote,
    _confidence,
    _dedupe_factors,
    _expected_move_pct,
    _intraday_position,
    _max_drawdown,
    _risk_penalty,
    _score_intraday,
    _score_momentum,
    _score_support_resistance,
    _score_trend,
    _score_volatility,
    _score_volume,
    average_true_range_percent,
    clean_history,
    exponential_moving_average,
    support_resistance,
)
from domain.models import FactorScore, IndicatorSnapshot


def _quote():
    # last==previous_close → change_pct=0，便于隔离 _risk_penalty/_score_* 的其它分支。
    return make_quote("600519", 10.0, 10.0, 10.2, 9.8, 10.0)


class IndicatorGuardTests(unittest.TestCase):
    def test_exponential_moving_average_none_for_short_series_else_final_ema(self):
        # 序列短于 period → _ema_series 返回 []，故 EMA 为 None；足够长时返回最后一个 EMA 值。
        self.assertIsNone(exponential_moving_average([1.0, 2.0], 5))
        self.assertAlmostEqual(exponential_moving_average([float(i) for i in range(10)], 3), 8.0)

    def test_atr_percent_none_when_first_window_close_non_finite(self):
        # 窗口首根的昨收非有限 → previous_close 守卫直接返回 None（不产出 NaN 的 ATR）。
        history = make_history(start=10, step=0.1, days=20)
        window = [replace(history[-15], close=float("nan")), *history[-14:]]
        self.assertIsNone(average_true_range_percent(window, 10.0, period=14))

    def test_support_resistance_none_when_no_finite_positive_extremes(self):
        # 窗口内无任何有限为正的高/低 → 返回 (None, None)，不落到 min/max 空序列。
        bar = make_history(days=1)[-1]
        bad = [replace(bar, low=float("nan"), high=float("nan"))]
        self.assertEqual(support_resistance(bad, window=20), (None, None))


class ScoreTrendGuardTests(unittest.TestCase):
    def test_non_finite_closes_skip_both_slope_blocks(self):
        # 末值非有限使 5 日 / 20 日均线均算不出（moving_average→None），两个斜率块都跳过，趋势记 0。
        closes = [10.0 + i * 0.1 for i in range(40)]
        closes[-1] = float("inf")
        factor, _reasons, _risks = _score_trend(closes, None, None)
        self.assertEqual(factor.score, 0)
        self.assertEqual(factor.verdict, "中性")

    def test_win_rate_in_neutral_band_contributes_nothing(self):
        # 胜率落在 (0.3, 0.7) 中性带：既不加 5 也不减 5，score 完全来自 +12 的短期斜率。
        factor, _reasons, _risks = _score_trend([10.0 + i for i in range(25)], 0.5, None)
        self.assertEqual(factor.score, 12)


class ScoreMomentumGuardTests(unittest.TestCase):
    def test_rsi_healthy_band_adds_eight(self):
        factor, reasons, _risks = _score_momentum(60.0, None)
        self.assertEqual(factor.score, 8)
        self.assertEqual(factor.verdict, "偏多")
        self.assertTrue(any("RSI14=60.0" in reason for reason in reasons))

    def test_significant_but_inconsistent_macd_confirms_nothing(self):
        # 柱体够大（过了 0.08/0.001 的过滤），但快线在信号线上方却柱体为负 → 两个方向确认都不成立，
        # MACD 贡献 0；rsi 缺失也不加分，故动量记 0。
        factor, _reasons, risks = _score_momentum(None, (1.0, 0.5, -0.5))
        self.assertEqual(factor.score, 0)
        self.assertEqual(factor.verdict, "中性")
        self.assertTrue(any("RSI样本不足" in risk for risk in risks))


class ScoreVolumeIntradayGuardTests(unittest.TestCase):
    def test_low_volume_ratio_scores_minus_four(self):
        factor, _reasons, _risks = _score_volume(_quote(), 0.5)
        self.assertEqual(factor.score, -4)
        self.assertEqual(factor.verdict, "低量")

    def test_intraday_position_none_is_invalid_zero(self):
        factor, _reasons, risks = _score_intraday(_quote(), None)
        self.assertEqual(factor.score, 0)
        self.assertEqual(factor.verdict, "无效")
        self.assertTrue(risks)

    def test_intraday_low_position_scores_minus_five(self):
        # 涨跌幅为 0（既非强势>=0.8，也非弱势<=-0.8），但日内位置<0.2 → 偏弱 -5。
        factor, _reasons, _risks = _score_intraday(_quote(), 0.1)
        self.assertEqual(factor.score, -5)
        self.assertEqual(factor.verdict, "偏弱")


class ScoreSupportResistanceGuardTests(unittest.TestCase):
    def test_upper_room_dominant_scores_plus_three(self):
        # 现价贴近支撑、远离压力：上行空间 > 下行空间*1.5 → 赔率略偏正 +3。
        factor, _reasons, _risks = _score_support_resistance(10.0, 9.9, 13.0)
        self.assertEqual(factor.score, 3)
        self.assertEqual(factor.verdict, "偏多")

    def test_balanced_room_scores_zero(self):
        # 上下空间对称（都不超过对方的 1.5 倍）→ 既不加也不减，中性 0。
        factor, _reasons, _risks = _score_support_resistance(10.0, 9.0, 11.0)
        self.assertEqual(factor.score, 0)
        self.assertEqual(factor.verdict, "中性")


class ScoreVolatilityGuardTests(unittest.TestCase):
    def test_high_atr_scores_minus_ten(self):
        factor, _reasons, _risks = _score_volatility(7.0)
        self.assertEqual(factor.score, -10)
        self.assertEqual(factor.verdict, "高波动")

    def test_mid_high_atr_scores_minus_four(self):
        factor, _reasons, _risks = _score_volatility(4.0)
        self.assertEqual(factor.score, -4)
        self.assertEqual(factor.verdict, "中高波动")


class RiskPenaltyGuardTests(unittest.TestCase):
    def test_non_positive_previous_close_skips_gap_block(self):
        # 昨收<=0 时跳过跳空判断（measure 的清洗保证不会发生，此处直测守卫）。
        penalty, risks = _risk_penalty(replace(_quote(), previous_close=0.0), [])
        self.assertEqual(penalty, 0)
        self.assertEqual(risks, [])

    def test_high_gap_up_penalizes_eight(self):
        # 开盘较昨收高开 10%（>4），振幅很小以隔离跳空项：仅扣 8。
        quote = make_quote("600519", 10.0, 11.0, 11.0, 10.9, 10.0)
        penalty, risks = _risk_penalty(quote, [])
        self.assertEqual(penalty, -8)
        self.assertTrue(any("高开" in risk for risk in risks))

    def test_low_gap_down_penalizes_six(self):
        # 低开 10%（<-4），振幅很小以隔离跳空项：仅扣 6。
        quote = make_quote("600519", 10.0, 9.0, 9.1, 9.0, 10.0)
        penalty, risks = _risk_penalty(quote, [])
        self.assertEqual(penalty, -6)
        self.assertTrue(any("低开" in risk for risk in risks))

    def test_non_positive_low_skips_amplitude_block(self):
        # 最低价<=0 时跳过振幅判断；昨收正常（gap=0 不扣）→ 合计 0。
        penalty, risks = _risk_penalty(replace(_quote(), low=0.0, previous_close=10.0), [])
        self.assertEqual(penalty, 0)
        self.assertEqual(risks, [])


class MiscEngineGuardTests(unittest.TestCase):
    def test_max_drawdown_zero_when_peak_never_positive(self):
        # 峰值恒非正（全 0 序列）→ peak>0 守卫始终为假，回撤记 0.0，不做除法。
        self.assertEqual(_max_drawdown([0.0, 0.0]), 0.0)

    def test_intraday_position_none_for_zero_span(self):
        # 当日高==低（区间为 0）→ 无法定位日内位置，返回 None。
        self.assertIsNone(_intraday_position(replace(_quote(), high=10.0, low=10.0)))

    def test_confidence_high_volatility_deducts_six(self):
        # ATR>6 的高波动扣 6 分置信度：同参数下 atr=7 比 atr=5 正好低 6。
        fields = dict(
            ma5=10.0,
            ma20=10.0,
            ma60=10.0,
            rsi14=55.0,
            macd=0.1,
            macd_signal=0.05,
            macd_histogram=0.05,
            bollinger_position=0.6,
            support=9.0,
            resistance=11.0,
            five_day_win_rate=0.6,
            max_drawdown_20=5.0,
            volume_ratio=1.4,
            intraday_position=0.6,
        )
        history = make_history(days=80)
        hi_vol = _confidence(40, history, IndicatorSnapshot(atr_percent=7.0, **fields))
        lo_vol = _confidence(40, history, IndicatorSnapshot(atr_percent=5.0, **fields))
        self.assertEqual(hi_vol, 75)
        self.assertEqual(lo_vol, 81)
        self.assertEqual(lo_vol - hi_vol, 6)

    def test_expected_move_none_without_atr_and_invalid_low(self):
        # 无 ATR 且最低价<=0（无法用日内振幅兜底）→ 预期波动为 None。
        self.assertIsNone(_expected_move_pct(replace(_quote(), low=0.0), None))

    def test_dedupe_factors_keeps_first_of_duplicate_name(self):
        deduped = _dedupe_factors(
            [FactorScore("重复", 1, 5, "a", "b"), FactorScore("重复", 2, 5, "c", "d")]
        )
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].score, 1)

    def test_clean_quote_recomputes_non_finite_change_pct(self):
        # change_pct 非有限 → 用 (最新价-昨收)/昨收*100 重算：(11-10)/10*100 = 10.0。
        cleaned = _clean_quote(
            replace(_quote(), last=11.0, previous_close=10.0, change_pct=float("nan"))
        )
        self.assertEqual(cleaned.change_pct, 10.0)

    def test_clean_history_drops_bar_with_negative_volume(self):
        # 价格有限为正但成交量为负 → 该根被剔除（非负性守卫）。
        bar = make_history(days=1)[-1]
        self.assertEqual(clean_history([replace(bar, volume=-5)]), [])


if __name__ == "__main__":
    unittest.main()
