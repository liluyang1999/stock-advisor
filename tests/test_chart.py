import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stock_advisor.chart import (
    index_to_x,
    price_to_y,
    moving_average_series,
    candle_layout,
    price_bounds,
    nearest_index,
    volume_heights,
)
from stock_advisor.models import DailyBar
from test_engine import make_history


class ChartTests(unittest.TestCase):
    def test_price_to_y_inverted_and_bounded(self):
        self.assertAlmostEqual(price_to_y(10, 10, 20, 0, 100), 100)  # 最低价在底部
        self.assertAlmostEqual(price_to_y(20, 10, 20, 0, 100), 0)    # 最高价在顶部
        self.assertAlmostEqual(price_to_y(15, 10, 20, 0, 100), 50)

    def test_price_to_y_flat_range_midline(self):
        self.assertAlmostEqual(price_to_y(10, 10, 10, 0, 100), 50)

    def test_price_to_y_rejects_non_finite_and_clamps_outliers(self):
        self.assertAlmostEqual(price_to_y(float("nan"), 10, 20, 0, 100), 50)
        self.assertAlmostEqual(price_to_y(float("inf"), 10, 20, 0, 100), 50)
        self.assertAlmostEqual(price_to_y(30, 10, 20, 0, 100), 0)
        self.assertAlmostEqual(price_to_y(0, 10, 20, 0, 100), 100)
        self.assertAlmostEqual(price_to_y(12, 10, float("inf"), 0, 100), 50)

    def test_index_to_x_spreads(self):
        xs = [index_to_x(i, 5, 0, 100) for i in range(5)]
        self.assertTrue(all(xs[i] < xs[i + 1] for i in range(4)))
        self.assertAlmostEqual(xs[0], 0)
        self.assertAlmostEqual(xs[-1], 100)

    def test_index_to_x_single(self):
        self.assertAlmostEqual(index_to_x(0, 1, 0, 100), 50)

    def test_ma_warmup_none(self):
        s = moving_average_series([1, 2, 3, 4, 5], 3)
        self.assertEqual(s[:2], [None, None])
        self.assertAlmostEqual(s[2], 2.0)
        self.assertAlmostEqual(s[4], 4.0)

    def test_ma_invalid_window_returns_empty_series(self):
        self.assertEqual(moving_average_series([1, 2, 3], 0), [None, None, None])
        self.assertEqual(moving_average_series([1, 2, 3], -2), [None, None, None])

    def test_ma_non_finite_windows_do_not_emit_non_finite_values(self):
        series = moving_average_series([1, 2, float("inf"), 4, float("nan"), 6, 7, 8], 3)
        self.assertEqual(series[:7], [None, None, None, None, None, None, None])
        self.assertAlmostEqual(series[7], 7.0)

    def test_candle_layout_orientation(self):
        bars = make_history(start=10, step=0.2, days=10)  # 上涨 → 阳线
        layout = candle_layout(bars, 0, 100, 0, 100)
        self.assertEqual(len(layout), 10)
        self.assertTrue(all("up" in c for c in layout))
        self.assertTrue(all(c["up"] for c in layout))
        # 阳线实体上沿(更高价)的 y 应不大于下沿(更低价)的 y
        self.assertTrue(all(c["body_top"] <= c["body_bottom"] for c in layout))

    def test_price_bounds_empty_safe(self):
        self.assertEqual(price_bounds([]), (0.0, 1.0))

    def test_price_bounds_uses_valid_ohlc_values_only(self):
        bars = [
            DailyBar("2026-01-01", 10.0, 11.0, float("inf"), float("nan"), 100, 1000.0, 1.0, 1.0),
            DailyBar("2026-01-02", -1.0, 12.0, 0.0, -5.0, 100, 1000.0, 1.0, 1.0),
        ]

        self.assertEqual(price_bounds(bars), (10.0, 12.0))

    def test_candle_layout_sanitizes_non_finite_bars(self):
        bars = [
            DailyBar("2026-01-01", 10.0, 11.0, 11.2, 9.8, 100, 1000.0, 1.0, 1.0),
            DailyBar("2026-01-02", float("nan"), float("inf"), float("inf"), -5.0, 100, 1000.0, 1.0, 1.0),
            DailyBar("2026-01-03", 11.0, 10.5, 11.4, 10.2, 100, 1000.0, -1.0, 1.0),
        ]

        layout = candle_layout(bars, 0, 100, 10, 80)

        self.assertEqual(len(layout), len(bars))
        for cell in layout:
            for key in ("x", "wick_top", "wick_bottom", "body_top", "body_bottom"):
                self.assertTrue(math.isfinite(cell[key]), key)
                self.assertGreaterEqual(cell[key], 0)
                self.assertLessEqual(cell[key], 100)
            self.assertLessEqual(cell["wick_top"], cell["wick_bottom"])
            self.assertLessEqual(cell["body_top"], cell["body_bottom"])

    def test_volume_heights_ignore_non_finite_and_negative_values(self):
        bars = [
            DailyBar("2026-01-01", 10.0, 10.2, 10.3, 9.9, 100, 1000.0, 1.0, 1.0),
            DailyBar("2026-01-02", 10.2, 10.1, 10.4, 10.0, float("inf"), 1000.0, -1.0, 1.0),
            DailyBar("2026-01-03", 10.1, 10.5, 10.6, 10.0, 200, 1000.0, 1.0, 1.0),
            DailyBar("2026-01-04", 10.5, 10.4, 10.6, 10.2, -20, 1000.0, -1.0, 1.0),
            DailyBar("2026-01-05", 10.4, 10.6, 10.7, 10.3, float("nan"), 1000.0, 1.0, 1.0),
        ]

        self.assertEqual(volume_heights(bars, 40), [20.0, 0.0, 40.0, 0.0, 0.0])
        self.assertEqual(volume_heights(bars, float("nan")), [0.0] * len(bars))

    def test_nearest_index(self):
        layout = [{"x": 0}, {"x": 10}, {"x": 20}, {"x": 30}]
        self.assertEqual(nearest_index(-5, layout), 0)
        self.assertEqual(nearest_index(12, layout), 1)
        self.assertEqual(nearest_index(26, layout), 3)
        self.assertEqual(nearest_index(100, layout), 3)
        self.assertEqual(nearest_index(5, []), -1)

    def test_nearest_index_ignores_invalid_layout_points(self):
        layout = [{"x": float("nan")}, {"x": 10}, {"x": float("inf")}, {"x": 30}]
        self.assertEqual(nearest_index(12, layout), 1)
        self.assertEqual(nearest_index(float("nan"), layout), -1)


if __name__ == "__main__":
    unittest.main()
