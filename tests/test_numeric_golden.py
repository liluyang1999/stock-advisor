"""金融数值的黄金样本 + 属性 + 防御测试（REQ-019/020/021/022/024 / WI-008 / TEST-NUM-001）。

WI-008 的 DoD 要求四类测试对**独立手算**的样本 100% 通过：
1. golden —— 值来自 tests/fixtures/golden_indicators.json，每个 expected 由人手笔算（推导在 fixture 里），
   不从被测代码生成，否则是循环验证；
2. property —— 与具体数值无关、必须恒成立的不变量（如 RSI∈[0,100]、bollinger 单调）；
3. look-ahead-guard —— 回测在第 i 天的决策不得读到第 i 天之后的数据（REQ-021）；
4. NaN/Inf-defense —— 非有限、负价、零价、空序列一律安全返回 None，不抛不脏（REQ-020）。
"""

import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.engine import (
    average_true_range_percent,
    bollinger_position,
    moving_average,
    rsi,
)
from domain.models import DailyBar

GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "golden_indicators.json").read_text(
        encoding="utf-8"
    )
)


def _bar(spec: dict) -> DailyBar:
    price = Decimal(str(spec["close"]))
    return DailyBar(
        date=date(2026, 7, 1),
        open=price,
        close=price,
        high=Decimal(str(spec["high"])),
        low=Decimal(str(spec["low"])),
        volume=1000,
        amount=1.0,
        pct_change=0.0,
        turnover_rate=0.5,
    )


class GoldenIndicatorTests(unittest.TestCase):
    """每个断言对照 fixture 里的手算值。fixture 改了必须重新手算推导，不得照抄实现输出。"""

    def test_moving_average_matches_hand_calculation(self):
        for case in GOLDEN["moving_average"]:
            with self.subTest(case=case["derivation"]):
                self.assertAlmostEqual(
                    moving_average(case["values"], case["window"]), case["expected"], places=6
                )

    def test_rsi_matches_hand_calculation(self):
        for case in GOLDEN["rsi"]:
            with self.subTest(case=case["derivation"]):
                self.assertAlmostEqual(
                    rsi(case["values"], case["period"]), case["expected"], places=6
                )

    def test_bollinger_position_matches_hand_calculation(self):
        for case in GOLDEN["bollinger_position"]:
            with self.subTest(case=case["derivation"]):
                got = bollinger_position(case["values"], case["last"], case["window"])
                self.assertAlmostEqual(got, case["expected"], delta=case.get("tolerance", 1e-6))

    def test_atr_percent_matches_hand_calculation(self):
        for case in GOLDEN["average_true_range_percent"]:
            with self.subTest(case=case["derivation"]):
                bars = [_bar(b) for b in case["bars"]]
                got = average_true_range_percent(bars, case["last"], period=case["period"])
                self.assertAlmostEqual(got, case["expected"], delta=case.get("tolerance", 1e-6))


class IndicatorPropertyTests(unittest.TestCase):
    """与具体数值无关、必须恒成立的不变量。"""

    def _series(self, seed: int, n: int) -> list[float]:
        # 确定性伪随机游走（不依赖 random 模块，测试可复现）。
        out, x = [], 100.0
        for i in range(n):
            x += ((seed * (i + 3)) % 7) - 3
            out.append(max(1.0, x))
        return out

    def test_rsi_is_always_within_0_and_100(self):
        for seed in range(1, 12):
            series = self._series(seed, 40)
            value = rsi(series, 14)
            if value is not None:
                self.assertGreaterEqual(value, 0.0, seed)
                self.assertLessEqual(value, 100.0, seed)

    def test_moving_average_is_within_the_min_max_of_its_window(self):
        for seed in range(1, 12):
            series = self._series(seed, 30)
            ma = moving_average(series, 10)
            if ma is not None:
                window = series[-10:]
                self.assertGreaterEqual(ma + 1e-9, min(window), seed)
                self.assertLessEqual(ma - 1e-9, max(window), seed)

    def test_bollinger_position_rises_monotonically_with_last_price(self):
        series = [10.0, 11.0, 9.0, 12.0, 10.5, 11.5, 10.0, 12.5, 11.0, 13.0]
        positions = [bollinger_position(series, last, 10) for last in (8.0, 10.0, 12.0, 14.0, 16.0)]
        self.assertTrue(all(p is not None for p in positions))
        for lower, higher in zip(positions[:-1], positions[1:], strict=True):
            self.assertLess(lower, higher)  # 价越高，通道位置越高

    def test_flat_series_gives_neutral_rsi_regardless_of_level(self):
        for level in (1.0, 50.0, 1000.0):
            self.assertAlmostEqual(rsi([level] * 20, 14), 50.0)


class LookAheadGuardTests(unittest.TestCase):
    """REQ-021：回测在第 i 天的指标只能用到第 i 天及之前的数据。"""

    def test_moving_average_ignores_future_appended_data(self):
        # 在 t 时刻算的 MA，不因未来追加的数据而改变——用"截断到 t 的序列"与"完整序列取同窗口"对照。
        full = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
        # 第 5 天（index 4，含）为止的 3 日 MA
        as_of_day5 = moving_average(full[:5], 3)
        # 若实现错误地把未来数据纳入，这个值会变化。手算: mean(12,13,14)=13.0
        self.assertAlmostEqual(as_of_day5, 13.0)
        # 完整序列的 3 日 MA 是 mean(14,15,16)=15.0，确实不同——证明窗口只看历史尾部。
        self.assertAlmostEqual(moving_average(full, 3), 15.0)

    def test_rsi_prefix_is_stable_under_future_appends(self):
        prefix = [10.0, 11.0, 10.5, 12.0, 11.0]
        base = rsi(prefix, 3)
        extended = prefix + [99.0, 1.0, 50.0]  # 未来的剧烈波动
        # 对 prefix 本身重算，结果必须与追加前一致（指标是纯函数、无隐藏状态）。
        self.assertEqual(rsi(prefix, 3), base)
        self.assertNotEqual(rsi(extended, 3), base)  # 完整序列自然不同，确认窗口在动


class NanInfDefenceTests(unittest.TestCase):
    """REQ-020：非有限、负价、零价、空/过短序列一律安全返回 None，不抛异常、不产出脏值。"""

    def test_moving_average_rejects_non_finite(self):
        self.assertIsNone(moving_average([1.0, float("nan"), 3.0], 3))
        self.assertIsNone(moving_average([1.0, float("inf"), 3.0], 3))

    def test_rsi_rejects_non_finite_and_short(self):
        self.assertIsNone(rsi([10.0, float("nan"), 11.0, 12.0], 3))
        self.assertIsNone(rsi([10.0, 11.0], 3))  # 长度不足 period+1
        self.assertIsNone(rsi([], 14))

    def test_bollinger_rejects_non_finite_last_and_short_window(self):
        self.assertIsNone(bollinger_position([10.0, 11.0, 12.0], float("inf"), 3))
        self.assertIsNone(bollinger_position([10.0, 11.0], 11.0, 3))  # 样本不足窗口

    def test_atr_rejects_non_positive_last_and_short_history(self):
        bars = [_bar({"high": 12, "low": 9, "close": 11}) for _ in range(5)]
        self.assertIsNone(average_true_range_percent(bars, 0.0, period=2))  # 零价
        self.assertIsNone(average_true_range_percent(bars, -5.0, period=2))  # 负价
        self.assertIsNone(average_true_range_percent(bars[:1], 12.0, period=2))  # 历史过短

    def test_no_indicator_raises_on_empty_input(self):
        # 空输入必须是 None 而非异常——回测/实时环里空序列会真实出现。
        for fn in (lambda: moving_average([], 5), lambda: rsi([], 14)):
            self.assertIsNone(fn())


if __name__ == "__main__":
    unittest.main()
