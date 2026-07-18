"""切档重判契约（REQ-003 / WI-011 / TEST-QT-AN-002 的框架无关半）。

REQ-003：Measurement 与 L1–L5 Decision 分离，**切档只重判缓存、不联网**。这里测那条重判逻辑
是纯函数——只吃一个已缓存的 Measurement 与目标档位，产出该档 AnalysisResult，全程不碰 provider、
不发网络请求。Qt 侧的档位控件只调用它（另测）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import make_measurement

from stock_advisor.domain.models import LEVEL_NAMES
from stock_advisor.services.tier_switch import redecide_all_levels, redecide_at_level


class RedecideTests(unittest.TestCase):
    def setUp(self):
        # 一次测量，缓存下来供各档重判——模拟"分析已完成、用户来回切档"。
        self.measurement = make_measurement()

    def test_redecide_at_level_needs_no_provider_and_no_network(self):
        # 关键契约：只吃 Measurement 与 level，签名里根本没有 provider —— 结构上不可能联网。
        result = redecide_at_level(self.measurement, 5)
        self.assertEqual(result.symbol, self.measurement.symbol)
        self.assertIn(result.action, ("BUY", "SELL", "HOLD"))

    def test_every_level_produces_a_result_from_the_same_measurement(self):
        results = redecide_all_levels(self.measurement)
        self.assertEqual(set(results), set(LEVEL_NAMES))  # 1..5 全覆盖
        for result in results.values():
            self.assertEqual(result.symbol, self.measurement.symbol)
            self.assertEqual(result.last, self.measurement.last)  # 报价不变（同一测量）

    def test_switching_levels_only_rejudges_never_remeasures(self):
        # 不同档的报价/因子测量恒等（同一 Measurement），只有决策口径变。
        r3 = redecide_at_level(self.measurement, 3)
        r5 = redecide_at_level(self.measurement, 5)
        self.assertEqual(r3.last, r5.last)
        self.assertEqual(r3.change_pct, r5.change_pct)
        self.assertEqual([f.name for f in r3.factor_scores], [f.name for f in r5.factor_scores])

    def test_more_aggressive_level_never_suggests_smaller_position_on_buy(self):
        # 档位单调性的合理性检查：更激进档在同一测量上，买入仓位不应更小。
        results = redecide_all_levels(self.measurement)
        buys = {lvl: r for lvl, r in results.items() if r.action == "BUY"}
        if len(buys) >= 2:
            ordered = sorted(buys)
            for lower, higher in zip(ordered[:-1], ordered[1:], strict=True):
                self.assertLessEqual(
                    buys[lower].suggested_position, buys[higher].suggested_position + 1e-9
                )

    def test_out_of_range_level_clamps_to_the_nearest_boundary(self):
        # 实证 policy.clamp_level 的口径：越界档钳制到最近边界，不回落标准档、不抛。
        # 99 -> 激进档(5)，0/-1 -> 稳健档(1)。
        self.assertEqual(
            redecide_at_level(self.measurement, 99).suggested_position,
            redecide_at_level(self.measurement, 5).suggested_position,
        )
        self.assertEqual(
            redecide_at_level(self.measurement, 0).suggested_position,
            redecide_at_level(self.measurement, 1).suggested_position,
        )


if __name__ == "__main__":
    unittest.main()
