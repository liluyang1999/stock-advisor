import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import make_history, make_quote

from domain.engine import _score_bollinger, analyze_stock, measure
from domain.policy import decide


class MeasureTests(unittest.TestCase):
    def test_measure_is_level_independent(self):
        h = make_history(start=20, step=0.25, days=80)
        q = make_quote("600519", 41.0, 40.2, 41.2, 39.9, 40.0, volume=260000)
        m = measure(q, h)
        self.assertGreater(len(m.factors), 0)
        self.assertIsInstance(m.confidence, int)
        self.assertEqual(m.history_len, 80)
        # objective_score == base + penalty (history >= 30, no 0.75 adjust)
        self.assertEqual(m.objective_score, max(-100, min(100, m.base_factor_sum + m.risk_penalty)))

    def test_small_sample_down_weight_rounding_matches_policy_l3(self):
        # Task 4 Fix B: 历史<30 天时 engine 用 int(objective*0.75) 截断，policy 用
        # int(round(score*0.75)) 四舍五入，二者口径不一致会打破 policy.py 文档承诺的
        # "L3 档决策分等于客观综合分"。以下参数系针对 base_factor_sum+risk_penalty=26、
        # history_len<30 这一失配边界试出的最小复现用例（26*0.75=19.5 是截断/四舍五入
        # 分道扬镳之处：截断给 19，四舍五入给 20）。
        h = make_history(start=20.0, step=0.021, days=15)
        q = make_quote("600519", 20.409, 20.307, 20.588, 19.804, 19.882, volume=330647)
        m = measure(q, h)

        # 前置条件：确认确实落在 26 / <30 天这个边界上，否则下面的等式断言就没有意义。
        self.assertEqual(m.base_factor_sum + m.risk_penalty, 26)
        self.assertLess(m.history_len, 30)

        l3_score = decide(m, level=3).policy_score
        self.assertEqual(
            m.objective_score,
            l3_score,
            f"客观综合分({m.objective_score})与 L3 决策分({l3_score})取整口径不一致",
        )

    def test_standard_level_matches_default(self):
        h = make_history(start=20, step=0.25, days=80)
        q = make_quote("600519", 41.0, 40.2, 41.2, 39.9, 40.0, volume=260000)
        self.assertEqual(analyze_stock(q, h).action, analyze_stock(q, h, level=3).action)
        self.assertEqual(analyze_stock(q, h, level=3).action, "BUY")

    def test_aggressive_vs_conservative_on_same_stock(self):
        # 一只中性偏强的票：标准档可能观望，激进档可能买入
        h = make_history(start=20, step=0.12, days=80)
        q = make_quote("600519", 22.4, 22.2, 22.6, 22.0, 22.2, volume=160000)
        aggressive = analyze_stock(q, h, level=5)
        conservative = analyze_stock(q, h, level=1)
        order = {"SELL": 0, "HOLD": 1, "BUY": 2}
        self.assertGreaterEqual(order[aggressive.action], order[conservative.action])


class FactorDeclaredRangeTests(unittest.TestCase):
    """因子条按 min(1, |score|/max_abs_score) 绘制，故 max_abs_score 必须正好等于该因子
    真实可达的最大 |score|：声明偏小会让越界部分被裁成满格、彼此不可区分；声明偏大则因子
    条永远画不满、低估信号强度。两者都只影响展示，不影响客观分（客观分只累加 score）。"""

    @staticmethod
    def _quote_at_series_end(history, spread=0.005):
        last = float(history[-1].close)
        return make_quote(
            "600519",
            last,
            last,
            last * (1 + spread),
            last * (1 - spread),
            last * 1.01,
            volume=260000,
        )

    def test_trend_factor_negative_floor_stays_within_declared_max(self):
        # 趋势质量 的四项里只有回撤是单向扣分（-4），故负向底 -29 比正向顶 +25 深 4。
        # 稳定下跌序列同时点燃四项负分（5日斜率<-2、20日斜率<-1、胜率<=0.3、回撤>8），
        # 是打到 -29 的最小复现。此前声明 25，使 -25..-29 一律被裁成满格、无法区分。
        history = make_history(start=40.0, step=-0.15, days=80)
        trend = next(
            f
            for f in measure(self._quote_at_series_end(history), history).factors
            if f.name == "趋势质量"
        )
        self.assertEqual(trend.score, -29)
        self.assertLessEqual(abs(trend.score), trend.max_abs_score)

    def test_bollinger_declared_max_matches_its_reachable_score_set(self):
        # 布林位置 只有 {-6,-3,0,+6} 四种取值（各分支代表位置：样本不足/偏强/过热/破位/
        # 偏弱/中性）。此前声明 8，使因子条最多只画到 6/8=75%。
        factors = [_score_bollinger(p)[0] for p in (None, 0.7, 1.2, -0.1, 0.1, 0.4, 0.95)]
        self.assertEqual({f.max_abs_score for f in factors}, {6})
        self.assertEqual(max(abs(f.score) for f in factors), 6)

    def test_no_factor_score_exceeds_its_declared_max_abs(self):
        # 全 8 因子的通用不变量，覆盖上涨/下跌/横盘/短样本四种形态。
        for start, step, days in (
            (40.0, 0.25, 80),
            (40.0, -0.15, 80),
            (40.0, 0.0, 80),
            (40.0, -0.02, 35),
        ):
            with self.subTest(step=step, days=days):
                history = make_history(start=start, step=step, days=days)
                for factor in measure(self._quote_at_series_end(history, 0.02), history).factors:
                    self.assertLessEqual(
                        abs(factor.score), factor.max_abs_score, f"{factor.name} 越过声明量程"
                    )


if __name__ == "__main__":
    unittest.main()
