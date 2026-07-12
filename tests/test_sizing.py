import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stock_advisor.domain.policy import size_fraction, position_plan
from test_policy import make_measurement


class SizingTests(unittest.TestCase):
    def test_fraction_zero_for_non_buy(self):
        self.assertEqual(size_fraction(make_measurement(-30), 3), 0.0)  # SELL
        self.assertEqual(size_fraction(make_measurement(0), 3), 0.0)    # HOLD

    def test_fraction_monotonic_in_level_for_buy(self):
        m = make_measurement(40, confidence=80)
        fr = [size_fraction(m, lv) for lv in (1, 2, 3, 4, 5)]
        self.assertTrue(all(fr[i] <= fr[i + 1] + 1e-9 for i in range(4)))
        self.assertLessEqual(fr[4], 0.90)

    def test_fraction_grows_with_capital_risk_budget(self):
        m = make_measurement(40, confidence=80)
        self.assertGreater(size_fraction(m, 5), size_fraction(m, 1))

    def test_position_plan_lot_rounding_and_loss(self):
        m = make_measurement(40, confidence=80, atr=2.5)  # last=10.0
        plan = position_plan(m, 3, capital=100000)
        self.assertEqual(plan.shares % 100, 0)
        self.assertGreater(plan.shares, 0)
        self.assertAlmostEqual(plan.max_loss, plan.shares * (plan.entry - plan.stop_price), places=2)
        self.assertGreater(plan.target_price, plan.entry)
        self.assertLess(plan.stop_price, plan.entry)
        self.assertEqual(plan.lots, plan.shares // 100)

    def test_position_plan_fraction_reflects_actual_lot_rounded_cost(self):
        m = make_measurement(40, confidence=80, atr=2.5)
        plan = position_plan(m, 3, capital=100000)

        self.assertAlmostEqual(plan.fraction, plan.cost / 100000, places=4)

    def test_capital_too_small_zero_shares(self):
        m = make_measurement(40, confidence=80)  # last=10 → 1手≈1000元
        plan = position_plan(m, 1, capital=500)
        self.assertEqual(plan.shares, 0)
        self.assertEqual(plan.fraction, 0.0)
        self.assertIn("不足", plan.note)

    def test_hold_plan_has_note_no_long(self):
        plan = position_plan(make_measurement(0), 3, capital=100000)
        self.assertEqual(plan.shares, 0)
        self.assertTrue(plan.note)

    def test_capital_monotonic_shares(self):
        m = make_measurement(40, confidence=80)
        small = position_plan(m, 3, capital=50000).shares
        big = position_plan(m, 3, capital=200000).shares
        self.assertGreaterEqual(big, small)

    def test_non_positive_capital_never_creates_negative_position(self):
        m = make_measurement(40, confidence=80)
        for capital in (0, -100000):
            with self.subTest(capital=capital):
                plan = position_plan(m, 3, capital=capital)
                self.assertEqual(plan.shares, 0)
                self.assertEqual(plan.lots, 0)
                self.assertEqual(plan.cost, 0)
                self.assertEqual(plan.max_loss, 0)
                self.assertEqual(plan.max_loss_pct, 0)
                self.assertIn("本金", plan.note)

    def test_non_finite_capital_never_creates_position(self):
        m = make_measurement(40, confidence=80)
        for capital in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(capital=capital):
                plan = position_plan(m, 3, capital=capital)
                self.assertEqual(plan.shares, 0)
                self.assertEqual(plan.lots, 0)
                self.assertEqual(plan.cost, 0)
                self.assertEqual(plan.max_loss, 0)
                self.assertEqual(plan.max_loss_pct, 0)
                self.assertIn("本金", plan.note)

    def test_non_finite_confidence_never_creates_position(self):
        for confidence in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(confidence=confidence):
                m = replace(make_measurement(80), confidence=confidence)
                plan = position_plan(m, 3, capital=100000)

                self.assertEqual(plan.shares, 0)
                self.assertEqual(plan.lots, 0)
                self.assertEqual(plan.cost, 0)
                self.assertEqual(plan.max_loss, 0)
                self.assertIn("把握", plan.note)

    def test_invalid_entry_price_does_not_generate_negative_targets(self):
        m = replace(make_measurement(40, confidence=80), last=-5.0)
        plan = position_plan(m, 3, capital=100000)

        self.assertEqual(plan.shares, 0)
        self.assertEqual(plan.stop_price, 0)
        self.assertEqual(plan.target_price, 0)
        self.assertEqual(plan.cost, 0)
        self.assertEqual(plan.max_loss, 0)
        self.assertIn("价格无效", plan.note)

    def test_non_finite_entry_price_does_not_generate_targets(self):
        for last in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(last=last):
                m = replace(make_measurement(40, confidence=80), last=last)
                plan = position_plan(m, 3, capital=100000)

                self.assertEqual(plan.shares, 0)
                self.assertEqual(plan.stop_price, 0)
                self.assertEqual(plan.target_price, 0)
                self.assertEqual(plan.cost, 0)
                self.assertEqual(plan.max_loss, 0)
                self.assertIn("价格无效", plan.note)


if __name__ == "__main__":
    unittest.main()
