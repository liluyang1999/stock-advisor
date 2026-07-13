import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stock_advisor.domain.engine import measure, analyze_stock
from stock_advisor.domain.policy import decide
from test_engine import make_quote, make_history


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


if __name__ == "__main__":
    unittest.main()
