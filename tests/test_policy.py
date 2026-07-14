import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.domain.models import CORE_DISCLAIMER, FactorScore, IndicatorSnapshot, Measurement
from stock_advisor.domain.policy import (
    LEVELS,
    clamp_level,
    decide,
    level_spec,
    policy_score,
    spectrum,
)
from stock_advisor.domain.symbols import normalize_symbol
from stock_advisor.ui.theme import DISCLAIMER as THEME_DISCLAIMER


def make_measurement(objective_score, confidence=70, risk_penalty=0, atr=2.5, history_len=80):
    ind = IndicatorSnapshot(
        ma5=10,
        ma20=10,
        ma60=10,
        rsi14=55,
        macd=0.1,
        macd_signal=0.05,
        macd_histogram=0.05,
        bollinger_position=0.6,
        atr_percent=atr,
        support=9.0,
        resistance=11.0,
        five_day_win_rate=0.6,
        max_drawdown_20=5.0,
        volume_ratio=1.4,
        intraday_position=0.6,
    )
    base = objective_score - risk_penalty
    return Measurement(
        symbol=normalize_symbol("600519"),
        name="测试",
        last=10.0,
        change_pct=1.0,
        factors=[FactorScore("均线结构", base, 28, "偏多", "x")],
        risk_penalty=risk_penalty,
        base_factor_sum=base,
        objective_score=objective_score,
        confidence=confidence,
        indicators=ind,
        recent_closes=[9.0, 10.0] * 30,
        reasons=["r"],
        risks=["k"],
        history_len=history_len,
        expected_move_pct=atr,
    )


class PolicyTests(unittest.TestCase):
    def test_levels_complete_and_monotonic(self):
        self.assertEqual(set(LEVELS), {1, 2, 3, 4, 5})
        buys = [LEVELS[i].t_buy for i in range(1, 6)]
        sells = [LEVELS[i].t_sell for i in range(1, 6)]
        self.assertEqual(buys, sorted(buys, reverse=True))
        self.assertEqual(sells, sorted(sells, reverse=True))

    def test_clamp_level(self):
        self.assertEqual(clamp_level(0), 1)
        self.assertEqual(clamp_level(9), 5)
        self.assertEqual(level_spec(3).name, "标准")

    def test_clamp_level_defaults_invalid_values_to_standard(self):
        for raw in ("abc", float("nan"), float("inf"), None):
            with self.subTest(raw=raw):
                self.assertEqual(clamp_level(raw), 3)

    def test_standard_reproduces_thresholds(self):
        self.assertEqual(decide(make_measurement(25), 3).action, "BUY")
        self.assertEqual(decide(make_measurement(24), 3).action, "HOLD")
        self.assertEqual(decide(make_measurement(-25), 3).action, "SELL")

    def test_aggressive_buys_more_than_conservative(self):
        m = make_measurement(20)
        self.assertEqual(decide(m, 5).action, "BUY")
        self.assertEqual(decide(m, 1).action, "HOLD")

    def test_conservative_sells_more_readily(self):
        m = make_measurement(-18)
        self.assertEqual(decide(m, 1).action, "SELL")  # 卖出线 -15
        self.assertEqual(decide(m, 5).action, "HOLD")  # 卖出线 -42

    def test_confidence_gate_only_conservative(self):
        m = make_measurement(45, confidence=50)
        self.assertEqual(decide(m, 1).action, "HOLD")
        self.assertEqual(decide(m, 3).action, "BUY")

    def test_risk_weight_shifts_policy_score(self):
        m = make_measurement(objective_score=10, risk_penalty=-10)  # base=20
        self.assertEqual(decide(m, 5).action, "BUY")
        self.assertEqual(decide(m, 1).action, "HOLD")

    def test_decide_fields(self):
        d = decide(make_measurement(40, confidence=80), 3)
        self.assertEqual(d.action_label, "买入/加仓")
        self.assertEqual(d.level, 3)
        self.assertTrue(d.forecast_label)
        self.assertGreaterEqual(d.suggested_position, 0)

    def test_policy_score_safely_handles_non_finite_measurement_scores(self):
        m = replace(make_measurement(40), base_factor_sum=float("inf"), risk_penalty=float("nan"))

        self.assertEqual(policy_score(m, 3), 0)
        self.assertEqual(decide(m, 3).action, "HOLD")
        self.assertTrue(all(cell.action == "HOLD" for cell in spectrum(m, 3)))

    def test_decide_suppresses_non_finite_expected_move_text(self):
        m = replace(make_measurement(40), expected_move_pct=float("inf"))

        decision = decide(m, 3)

        self.assertNotIn("inf", decision.forecast_label.lower())
        self.assertTrue(math.isfinite(decision.suggested_position))

    def test_decide_never_buys_with_invalid_confidence(self):
        for confidence in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(confidence=confidence):
                m = replace(make_measurement(80), confidence=confidence)

                decision = decide(m, 3)

                self.assertEqual(decision.action, "HOLD")
                self.assertEqual(decision.suggested_position, 0)
                self.assertTrue(any("把握" in risk for risk in decision.risks))


class DisclaimerConsistencyTests(unittest.TestCase):
    """policy.py 追加到每条决策 risks 的免责句，须与 theme.py 的全文页脚免责声明措辞一致
    （同一核心句），不能各写各的。"""

    def test_decide_appends_the_canonical_core_disclaimer_to_risks(self):
        decision = decide(make_measurement(40, confidence=80), 3)
        self.assertIn(CORE_DISCLAIMER, decision.risks)

    def test_theme_footer_disclaimer_is_wording_consistent_with_the_core(self):
        # theme.py 为保持零项目内依赖不 import CORE_DISCLAIMER，因此用字面量对齐核心句
        # （去掉句末句号后作为前缀），由本测试兜底防止两处措辞再度漂移。
        core_sentence = CORE_DISCLAIMER.rstrip("。")
        self.assertTrue(THEME_DISCLAIMER.startswith(core_sentence))


if __name__ == "__main__":
    unittest.main()
